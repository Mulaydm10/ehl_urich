package com.bmwmotorrad.ridefit;

import android.app.Application;
import android.os.Build;
import android.util.Log;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * MySpin — the phone side of the BMW / Bosch mySPIN vehicle-data link.
 *
 * Live bike signals in the real BMW app (speed, RPM, gear, fuel, lean) come
 * over Bosch mySPIN, not over BLE GATT. The head unit only hands those signals
 * to an *authorised* application: mySPIN identifies each phone app by its AppId
 * (package name + signing certificate) and the head unit checks, per data key,
 * whether that app may read it (MySpinServerSDK.canAccessVehicleData(key)). So
 * pairing the phone is not enough — an unregistered app gets nothing, or at
 * most the three generic keys (geolocation / is-moving / is-night).
 *
 * Honesty rules:
 *  - The proprietary Bosch mySPIN SDK is NOT bundled in this repo. This plugin
 *    talks to it purely by reflection, so when the SDK class is absent every
 *    call reports "sdk.absent" and returns present=false. Nothing is faked.
 *  - When the SDK *is* present, we attempt registerApplication and, per key,
 *    canAccessVehicleData; we log exactly what the head unit grants or denies
 *    and only deliver a value the SDK actually delivered.
 *
 * Every step is written to a bounded trace ring buffer, emitted as a "trace"
 * event (so it joins the same live radio log, logcat and backend trail as
 * BikeLink) and — for values — as a "vehicleData" event.
 */
@CapacitorPlugin(name = "MySpin")
public class MySpinPlugin extends Plugin {

    private static final String TAG = "MySpin";
    private static final String SDK_CLASS = "com.bosch.myspin.serversdk.MySpinServerSDK";
    private static final int TRACE_LIMIT = 1000;

    /**
     * Vehicle-data keys we ask the head unit for, from the shipped BMW app's
     * Bosch key table (flowstate/docs). The first three are the SDK's public
     * generic keys; the rest are the richer BSOT keys an authorised app may
     * receive. We label each one on the callback so speed/lean can drive the UI.
     */
    private static final Map<Long, String> KEYS = new LinkedHashMap<>();
    static {
        KEYS.put(1L, "geolocation");
        KEYS.put(2L, "is_moving");
        KEYS.put(3L, "is_night");
        KEYS.put(2201960939L, "display_vehicle_speed");
        KEYS.put(2099443710L, "vehicle_speed_accurate");
        KEYS.put(2680898438L, "display_engine_speed");
        KEYS.put(258945671L, "actual_gear_position");
        KEYS.put(3812856091L, "fuel_level");
        KEYS.put(3025988756L, "distance_to_empty");
        KEYS.put(1120875974L, "lean_angle");        // ROLE_ANGLE
        KEYS.put(3732206196L, "pitch_angle");
        KEYS.put(1072423361L, "lateral_acceleration");
        KEYS.put(291948929L, "longitudinal_acceleration");
        KEYS.put(656363884L, "vehicle_mileage");
        KEYS.put(853173681L, "ambient_temp");
    }

    private final Deque<JSObject> trace = new ArrayDeque<>();
    private long traceSeq = 0;
    private long traceDropped = 0;
    private final String session = "ms-" + Long.toHexString(System.currentTimeMillis());

    private Object sdk;                 // MySpinServerSDK instance (reflection)
    private Class<?> sdkClass;
    private boolean sdkPresent = false;
    private boolean registered = false;
    private Object connectionListener;  // dynamic proxy, kept to unregister
    private final Map<Long, Object> keyListeners = new LinkedHashMap<>();

    @Override
    public void load() {
        try {
            sdkClass = Class.forName(SDK_CLASS);
            sdkPresent = true;
        } catch (Throwable t) {
            sdkPresent = false;
        }
        JSObject o = new JSObject();
        o.put("sdkPresent", sdkPresent);
        o.put("sdk", Build.VERSION.SDK_INT);
        o.put("device", Build.MANUFACTURER + " " + Build.MODEL);
        o.put("note", sdkPresent ? "" : "Bosch mySPIN SDK is not bundled in this build; vehicle data cannot be read on this phone.");
        emit("myspin.load", sdkPresent ? "info" : "warn", o);
    }

    // ------------------------------------------------------------------
    // trace (same shape as BikeLink so the panels/backend merge cleanly)
    // ------------------------------------------------------------------

    private void emit(String op, String level, JSObject fields) {
        JSObject e = fields == null ? new JSObject() : fields;
        e.put("seq", ++traceSeq);
        e.put("at", System.currentTimeMillis());
        e.put("op", op);
        e.put("level", level);
        e.put("source", "phone");
        e.put("session", session);
        synchronized (trace) {
            trace.addLast(e);
            while (trace.size() > TRACE_LIMIT) { trace.removeFirst(); traceDropped++; }
        }
        Log.d(TAG, op + " " + e);
        notifyListeners("trace", e);
    }

    private void emit(String op, JSObject fields) { emit(op, "info", fields); }

    private static JSObject f(String k, Object v) { JSObject o = new JSObject(); o.put(k, v); return o; }

    @PluginMethod
    public void getTrace(PluginCall call) {
        long since = call.getInt("since", 0);
        JSArray arr = new JSArray();
        synchronized (trace) { for (JSObject e : trace) if (e.optLong("seq") > since) arr.put(e); }
        JSObject o = new JSObject();
        o.put("events", arr);
        o.put("nextSeq", traceSeq + 1);
        o.put("dropped", traceDropped);
        o.put("session", session);
        call.resolve(o);
    }

    @PluginMethod
    public void clearTrace(PluginCall call) {
        synchronized (trace) { trace.clear(); }
        traceDropped = 0;
        JSObject o = new JSObject();
        o.put("nextSeq", traceSeq + 1);
        call.resolve(o);
    }

    // ------------------------------------------------------------------
    // state
    // ------------------------------------------------------------------

    private boolean invokeBool(String method, boolean fallback) {
        if (!sdkPresent || sdk == null) return fallback;
        try {
            Method m = sdkClass.getMethod(method);
            Object r = m.invoke(sdk);
            return r instanceof Boolean ? (Boolean) r : fallback;
        } catch (Throwable t) { return fallback; }
    }

    private void ensureInstance() {
        if (sdk != null || !sdkPresent) return;
        try {
            Method shared = sdkClass.getMethod("sharedInstance");
            sdk = shared.invoke(null);
        } catch (Throwable t) {
            emit("myspin.error", "error", f("detail", "sharedInstance failed: " + t));
        }
    }

    private JSObject state() {
        JSObject o = new JSObject();
        o.put("sdkPresent", sdkPresent);
        o.put("registered", registered);
        o.put("connected", invokeBool("isConnected", false));
        o.put("isTwoWheeler", invokeBool("isTwoWheeler", false));
        return o;
    }

    @PluginMethod
    public void getState(PluginCall call) {
        emit("myspin.state", state());
        call.resolve(state());
    }

    // ------------------------------------------------------------------
    // register the application with mySPIN
    // ------------------------------------------------------------------

    @PluginMethod
    public void register(PluginCall call) {
        if (!sdkPresent) {
            emit("myspin.register", "warn", f("ok", false));
            call.resolve(state());
            return;
        }
        ensureInstance();
        try {
            Application app = getActivity().getApplication();
            Method reg = sdkClass.getMethod("registerApplication", Application.class);
            reg.invoke(sdk, app);
            registered = true;
            emit("myspin.register", "info", f("ok", true));
            registerConnectionListener();
        } catch (Throwable t) {
            registered = false;
            emit("myspin.register", "error", f("detail", String.valueOf(t)));
        }
        call.resolve(state());
    }

    private void registerConnectionListener() {
        if (!sdkPresent || sdk == null || connectionListener != null) return;
        try {
            Class<?> listenerClass = Class.forName(SDK_CLASS + "$ConnectionStateListener");
            connectionListener = Proxy.newProxyInstance(
                listenerClass.getClassLoader(),
                new Class<?>[]{listenerClass},
                new InvocationHandler() {
                    @Override public Object invoke(Object proxy, Method method, Object[] args) {
                        if ("onConnectionStateChanged".equals(method.getName())) {
                            boolean connected = args != null && args.length > 0 && Boolean.TRUE.equals(args[0]);
                            JSObject o = new JSObject();
                            o.put("connected", connected);
                            o.put("isTwoWheeler", invokeBool("isTwoWheeler", false));
                            emit("myspin.connection", connected ? "info" : "warn", o);
                            notifyListeners("myspinState", state());
                            if (connected) subscribeAll();
                        }
                        return null;
                    }
                });
            Method m = sdkClass.getMethod("registerConnectionStateListener", listenerClass);
            m.invoke(sdk, connectionListener);
            emit("myspin.listener", f("what", "connectionState"));
        } catch (Throwable t) {
            emit("myspin.error", "error", f("detail", "connection listener failed: " + t));
        }
    }

    // ------------------------------------------------------------------
    // vehicle-data keys: per-key access check + subscription
    // ------------------------------------------------------------------

    @PluginMethod
    public void subscribe(PluginCall call) {
        subscribeAll();
        call.resolve(state());
    }

    private void subscribeAll() {
        if (!sdkPresent || sdk == null) {
            emit("myspin.subscribe", "warn", f("reason", "sdk_absent"));
            return;
        }
        for (Map.Entry<Long, String> entry : KEYS.entrySet()) {
            long key = entry.getKey();
            String name = entry.getValue();
            boolean granted;
            try {
                Method can = sdkClass.getMethod("canAccessVehicleData", long.class);
                Object r = can.invoke(sdk, key);
                granted = r instanceof Boolean && (Boolean) r;
            } catch (Throwable t) {
                emit("myspin.access", "error", access(name, key, false, String.valueOf(t)));
                continue;
            }
            emit("myspin.access", granted ? "info" : "warn", access(name, key, granted, null));
            if (granted) subscribeKey(key, name);
        }
    }

    private static JSObject access(String name, long key, boolean granted, String detail) {
        JSObject o = new JSObject();
        o.put("key", name);
        o.put("keyId", key);
        o.put("granted", granted);
        if (detail != null) o.put("detail", detail);
        return o;
    }

    private void subscribeKey(long key, String name) {
        if (keyListeners.containsKey(key)) return;
        try {
            Class<?> listenerClass = Class.forName("com.bosch.myspin.serversdk.VehicleDataListener");
            Object proxy = Proxy.newProxyInstance(
                listenerClass.getClassLoader(),
                new Class<?>[]{listenerClass},
                new InvocationHandler() {
                    @Override public Object invoke(Object p, Method method, Object[] args) {
                        if ("onVehicleDataUpdate".equals(method.getName()) && args != null && args.length >= 2) {
                            onVehicleData(key, name, args[1]);
                        }
                        return null;
                    }
                });
            Method m = sdkClass.getMethod("registerVehicleDataListenerForKey", listenerClass, long.class);
            m.invoke(sdk, proxy, key);
            keyListeners.put(key, proxy);
            emit("myspin.listener", f("what", name));
        } catch (Throwable t) {
            emit("myspin.error", "error", access(name, key, true, "subscribe failed: " + t));
        }
    }

    /** Read the value(s) out of a MySpinVehicleData bundle and publish them. */
    private void onVehicleData(long key, String name, Object data) {
        JSObject o = new JSObject();
        o.put("key", name);
        o.put("keyId", key);
        try {
            Method keys = data.getClass().getMethod("keys");
            Method get = data.getClass().getMethod("get", String.class);
            Object set = keys.invoke(data);
            JSObject values = new JSObject();
            if (set instanceof Iterable) {
                for (Object field : (Iterable<?>) set) {
                    Object v = get.invoke(data, String.valueOf(field));
                    values.put(String.valueOf(field), v == null ? null : String.valueOf(v));
                }
            }
            o.put("values", values);
        } catch (Throwable t) {
            o.put("detail", "parse failed: " + t);
        }
        emit("vehicle.data", o);
        notifyListeners("vehicleData", o);
    }

    @PluginMethod
    public void disconnect(PluginCall call) {
        if (sdkPresent && sdk != null) {
            for (Map.Entry<Long, Object> e : keyListeners.entrySet()) {
                try {
                    Class<?> lc = Class.forName("com.bosch.myspin.serversdk.VehicleDataListener");
                    Method m = sdkClass.getMethod("unregisterVehicleDataListenerForKey", lc, long.class);
                    m.invoke(sdk, e.getValue(), e.getKey());
                } catch (Throwable ignored) { }
            }
        }
        keyListeners.clear();
        emit("myspin.disconnect", f("ok", true));
        call.resolve(state());
    }
}
