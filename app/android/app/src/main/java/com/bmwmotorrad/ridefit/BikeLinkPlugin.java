package com.bmwmotorrad.ridefit;

import android.Manifest;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.BluetoothSocket;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.content.Context;
import android.os.Build;
import android.os.ParcelUuid;
import android.util.Log;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

/**
 * BikeLink — the phone side of the local phone <-> motorcycle link.
 *
 * Exposes BLE adapter state, scan, connect/disconnect, connection state and
 * "send route" to the web layer (app/src/services/bikeLink.ts). The backend
 * mirror lives in flowstate/app/bike_link.py (NativeBleTransport).
 *
 * Honesty rule: every result says exactly what happened on the radio. No
 * adapter -> {present:false}; no verified route characteristic -> the transfer
 * is rejected, never faked.
 *
 * UNVERIFIED: the real bike's GATT layout (service / characteristic UUIDs for
 * route transfer) and the mySPIN wire protocol were not captured (the analysis
 * emulator has no radio). sendRoute therefore takes the UUIDs as parameters
 * and refuses when the connected device does not expose them. Once the
 * protocol is sourced on a real bike, the constants can be pinned in
 * bikeLink.ts without changing this plugin's interface.
 *
 * Evidence from the decompiled BMW app (flowstate/docs/28): the head unit is
 * recognised as a *bonded Bluetooth Classic* device (name "ICC…" / "BMW
 * Motorrad …", SDP UUID c707050e-…) and driven over RFCOMM, not over BLE GATT.
 * listBondedDevices() and probeIccLink() exist to check that on real hardware;
 * probeIccLink only opens and closes an RFCOMM socket and reports the result —
 * it speaks no protocol and sends no route.
 *
 * Every radio operation is written to a bounded trace ring buffer, emitted as
 * a "trace" event and logged to logcat under TAG, so a ride next to the bike
 * can be debugged live from the app panel and from the backend trail.
 */
@CapacitorPlugin(
    name = "BikeLink",
    permissions = {
        @Permission(alias = "bluetooth", strings = {
            Manifest.permission.BLUETOOTH_SCAN,
            Manifest.permission.BLUETOOTH_CONNECT
        }),
        @Permission(alias = "location", strings = {
            Manifest.permission.ACCESS_FINE_LOCATION
        })
    }
)
public class BikeLinkPlugin extends Plugin {

    private static final String TAG = "BikeLink";
    private static final long CHUNK_DELAY_MS = 40;
    private static final int CHUNK_BYTES = 180;
    private static final int TRACE_LIMIT = 1000;

    /**
     * SDP service IDs the BMW app accepts for the bike head unit, read out of
     * com.bmw.connride.connectivity.bluetooth in the shipped APK. Used here to
     * *label* bonded devices and as the default RFCOMM probe target; they are
     * not GATT route-transfer UUIDs and are never used as such.
     */
    private static final String[] ICC_SERVICE_UUIDS = {
        "c707050e-efae-1449-3913-c191e5bb32dc",
        "a96f9e76-ab2e-869c-40e3-1da0c086a07a",
        "dc32bbe5-91c1-1339-4914-aeef0e0507c7"
    };

    private BluetoothAdapter adapter;
    private BluetoothLeScanner scanner;
    private BluetoothGatt gatt;
    private String connectedId;
    private String connectionState = "disconnected";
    private final Map<String, BluetoothDevice> seen = new LinkedHashMap<>();
    private final Map<String, Integer> rssi = new LinkedHashMap<>();
    private boolean scanning = false;

    // one in-flight transfer at a time
    private PluginCall pendingSend;
    private byte[] sendBuffer;
    private int sendOffset;
    private int sendChunkBytes = CHUNK_BYTES;
    private long sendStartedAt;
    private BluetoothGattCharacteristic sendCharacteristic;

    private final Deque<JSObject> trace = new ArrayDeque<>();
    private long traceSeq = 0;
    private long traceDropped = 0;
    private final String session = "bl-" + Long.toHexString(System.currentTimeMillis());

    @Override
    public void load() {
        BluetoothManager mgr = (BluetoothManager) getContext().getSystemService(Context.BLUETOOTH_SERVICE);
        adapter = mgr == null ? null : mgr.getAdapter();
        if (adapter == null) connectionState = "unavailable";
        JSObject o = new JSObject();
        o.put("adapterPresent", adapter != null);
        o.put("sdk", Build.VERSION.SDK_INT);
        o.put("device", Build.MANUFACTURER + " " + Build.MODEL);
        emit("plugin.load", adapter == null ? "warn" : "info", o);
    }

    // ------------------------------------------------------------------
    // trace
    // ------------------------------------------------------------------

    /** Record one radio event: ring buffer + "trace" listener + logcat. */
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

    private static JSObject f(String k, Object v) {
        JSObject o = new JSObject();
        o.put(k, v);
        return o;
    }

    /**
     * Addresses are stable identifiers for the bike; keep the OUI and the last
     * octet so two bikes can be told apart in a shared log without publishing
     * the full MAC.
     */
    private static String shortId(String address) {
        if (address == null || address.length() < 17) return String.valueOf(address);
        return address.substring(0, 8) + ":…:" + address.substring(15);
    }

    @PluginMethod
    public void getTrace(PluginCall call) {
        long since = call.getInt("since", 0);
        JSArray arr = new JSArray();
        synchronized (trace) {
            for (JSObject e : trace) if (e.optLong("seq") > since) arr.put(e);
        }
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
    // adapter / permissions
    // ------------------------------------------------------------------

    private JSObject adapterState() {
        JSObject o = new JSObject();
        boolean present = adapter != null;
        o.put("present", present);
        o.put("enabled", present && adapter.isEnabled());
        o.put("standIn", false);
        o.put("note", present ? "" : "No Bluetooth adapter on this device.");
        return o;
    }

    @PluginMethod
    public void getAdapterState(PluginCall call) {
        call.resolve(adapterState());
    }

    private boolean needsRuntimeBluetoothPermission() {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.S;
    }

    private boolean hasPermissions() {
        if (needsRuntimeBluetoothPermission()) return getPermissionState("bluetooth") == PermissionState.GRANTED;
        return getPermissionState("location") == PermissionState.GRANTED;
    }

    @PluginMethod
    public void requestBluetoothPermissions(PluginCall call) {
        String alias = needsRuntimeBluetoothPermission() ? "bluetooth" : "location";
        if (hasPermissions()) { emit("permission.already", f("alias", alias)); call.resolve(permissionsResult()); return; }
        emit("permission.request", f("alias", alias));
        requestPermissionForAlias(alias, call, "permissionsCallback");
    }

    @PermissionCallback
    private void permissionsCallback(PluginCall call) {
        boolean granted = hasPermissions();
        emit("permission.result", granted ? "info" : "warn", f("granted", granted));
        call.resolve(permissionsResult());
    }

    private JSObject permissionsResult() {
        JSObject o = new JSObject();
        o.put("granted", hasPermissions());
        return o;
    }

    // ------------------------------------------------------------------
    // scan
    // ------------------------------------------------------------------

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            BluetoothDevice d = result.getDevice();
            if (d == null) return;
            boolean isNew = !seen.containsKey(d.getAddress());
            seen.put(d.getAddress(), d);
            rssi.put(d.getAddress(), result.getRssi());
            JSObject dev = deviceJson(d, result.getRssi());
            if (isNew || dev.getBoolean("icc", false)) emit("scan.result", deviceJson(d, result.getRssi()));
            notifyListeners("device", dev);
        }

        @Override
        public void onScanFailed(int errorCode) {
            scanning = false;
            JSObject o = new JSObject();
            o.put("error", "BLE scan failed (code " + errorCode + ")");
            o.put("errorCode", errorCode);
            emit("scan.failed", "error", o);
            notifyListeners("scanFailed", o);
        }
    };

    private JSObject deviceJson(BluetoothDevice d, Integer signal) {
        return deviceJson(d, signal, "ble");
    }

    /**
     * One device as the web layer sees it. ``icc`` marks a device the BMW app
     * would treat as the bike head unit (name prefix or advertised SDP UUID);
     * it is a label for triage, not a claim that anything was negotiated.
     */
    private JSObject deviceJson(BluetoothDevice d, Integer signal, String kind) {
        JSObject o = new JSObject();
        o.put("id", d.getAddress());
        o.put("shortId", shortId(d.getAddress()));
        String name = null;
        try { name = d.getName(); } catch (SecurityException ignored) { /* BLUETOOTH_CONNECT missing */ }
        o.put("name", name == null ? ("ble".equals(kind) ? "Unnamed BLE device" : "Unnamed device") : name);
        o.put("rssi", signal);
        o.put("kind", kind);
        int bond = BluetoothDevice.BOND_NONE;
        try { bond = d.getBondState(); } catch (SecurityException ignored) { }
        o.put("paired", bond == BluetoothDevice.BOND_BONDED);
        o.put("bondState", bondName(bond));
        JSArray uuids = new JSArray();
        boolean iccUuid = false;
        try {
            ParcelUuid[] pu = d.getUuids();
            if (pu != null) {
                for (ParcelUuid p : pu) {
                    String u = p.getUuid().toString().toLowerCase(Locale.ROOT);
                    uuids.put(u);
                    for (String known : ICC_SERVICE_UUIDS) if (known.equals(u)) iccUuid = true;
                }
            }
        } catch (SecurityException ignored) { }
        o.put("sdpUuids", uuids);
        boolean iccName = name != null && (name.startsWith("ICC") || name.startsWith("BMW Motorrad"));
        o.put("icc", iccUuid || iccName);
        o.put("iccReason", iccUuid ? "sdp_uuid" : iccName ? "name_prefix" : null);
        o.put("standIn", false);
        return o;
    }

    private static String bondName(int bond) {
        if (bond == BluetoothDevice.BOND_BONDED) return "bonded";
        if (bond == BluetoothDevice.BOND_BONDING) return "bonding";
        return "none";
    }

    @PluginMethod
    public void startScan(PluginCall call) {
        if (adapter == null) { call.reject("No Bluetooth adapter on this device.", "NO_ADAPTER"); return; }
        if (!adapter.isEnabled()) { call.reject("Bluetooth is turned off.", "ADAPTER_OFF"); return; }
        if (!hasPermissions()) { call.reject("Bluetooth permission not granted.", "NO_PERMISSION"); return; }
        scanner = adapter.getBluetoothLeScanner();
        if (scanner == null) { call.reject("BLE scanner unavailable.", "NO_SCANNER"); return; }
        try {
            seen.clear();
            rssi.clear();
            scanner.startScan(scanCallback);
            scanning = true;
            emit("scan.start", new JSObject());
        } catch (SecurityException e) {
            emit("scan.start.denied", "error", f("error", String.valueOf(e.getMessage())));
            call.reject("Bluetooth permission not granted.", "NO_PERMISSION");
            return;
        }
        JSObject o = new JSObject();
        o.put("scanning", true);
        call.resolve(o);
    }

    @PluginMethod
    public void stopScan(PluginCall call) {
        if (scanner != null && scanning) {
            try { scanner.stopScan(scanCallback); } catch (SecurityException ignored) { }
        }
        scanning = false;
        JSObject o = new JSObject();
        o.put("scanning", false);
        o.put("devices", devicesArray());
        emit("scan.stop", f("found", seen.size()));
        call.resolve(o);
    }

    /**
     * Bonded Bluetooth Classic devices. The BMW app finds the head unit here
     * (system-level bonding), not by BLE advertising, so this is what a real
     * bike test has to look at first.
     */
    @PluginMethod
    public void listBondedDevices(PluginCall call) {
        if (adapter == null) { call.reject("No Bluetooth adapter on this device.", "NO_ADAPTER"); return; }
        if (!hasPermissions()) { call.reject("Bluetooth permission not granted.", "NO_PERMISSION"); return; }
        JSArray arr = new JSArray();
        int icc = 0;
        try {
            for (BluetoothDevice d : adapter.getBondedDevices()) {
                seen.put(d.getAddress(), d);
                JSObject o = deviceJson(d, null, "classic");
                if (o.getBoolean("icc", false)) icc++;
                arr.put(o);
            }
        } catch (SecurityException e) {
            call.reject("Bluetooth permission not granted.", "NO_PERMISSION");
            return;
        }
        JSObject res = new JSObject();
        res.put("devices", arr);
        emit("bonded.list", f("count", arr.length()).put("iccCandidates", icc));
        call.resolve(res);
    }

    /**
     * Open and immediately close an RFCOMM/SPP socket to a bonded device on one
     * of the BMW service UUIDs, to learn whether the bike accepts the classic
     * channel the BMW app uses. It exchanges no data and sends no route; a
     * successful probe proves the channel exists, nothing more.
     */
    @PluginMethod
    public void probeIccLink(PluginCall call) {
        String id = call.getString("deviceId");
        String uuid = call.getString("uuid", ICC_SERVICE_UUIDS[0]);
        if (adapter == null) { call.reject("No Bluetooth adapter on this device.", "NO_ADAPTER"); return; }
        if (id == null) { call.reject("deviceId is required."); return; }
        if (!hasPermissions()) { call.reject("Bluetooth permission not granted.", "NO_PERMISSION"); return; }
        final BluetoothDevice device;
        try { device = adapter.getRemoteDevice(id); }
        catch (IllegalArgumentException e) { call.reject("Unknown device " + id, "UNKNOWN_DEVICE"); return; }
        final UUID service;
        try { service = UUID.fromString(uuid); }
        catch (IllegalArgumentException e) { call.reject("Bad uuid.", "BAD_UUID"); return; }

        call.setKeepAlive(true);
        emit("icc.probe.start", f("device", shortId(id)).put("uuid", uuid));
        new Thread(() -> {
            long t0 = System.currentTimeMillis();
            BluetoothSocket socket = null;
            try {
                if (scanning && scanner != null) { try { scanner.stopScan(scanCallback); scanning = false; } catch (SecurityException ignored) { } }
                socket = device.createRfcommSocketToServiceRecord(service);
                socket.connect();
                long ms = System.currentTimeMillis() - t0;
                JSObject o = new JSObject();
                o.put("ok", true);
                o.put("elapsedMs", ms);
                o.put("uuid", uuid);
                o.put("message", "RFCOMM channel " + uuid + " accepted the connection in " + ms
                    + " ms. The channel exists; no protocol was spoken and nothing was sent.");
                emit("icc.probe.ok", o);
                call.resolve(o);
            } catch (IOException | SecurityException e) {
                long ms = System.currentTimeMillis() - t0;
                JSObject o = new JSObject();
                o.put("ok", false);
                o.put("elapsedMs", ms);
                o.put("uuid", uuid);
                o.put("error", e.getClass().getSimpleName() + ": " + e.getMessage());
                o.put("message", "RFCOMM channel " + uuid + " refused the connection after " + ms + " ms.");
                emit("icc.probe.failed", "warn", o);
                call.resolve(o);
            } finally {
                if (socket != null) { try { socket.close(); } catch (IOException ignored) { } }
                call.setKeepAlive(false);
            }
        }, "bikelink-icc-probe").start();
    }

    private JSArray devicesArray() {
        JSArray arr = new JSArray();
        for (BluetoothDevice d : seen.values()) arr.put(deviceJson(d, rssi.get(d.getAddress())));
        return arr;
    }

    @PluginMethod
    public void getDevices(PluginCall call) {
        JSObject o = new JSObject();
        o.put("scanning", scanning);
        o.put("devices", devicesArray());
        call.resolve(o);
    }

    // ------------------------------------------------------------------
    // connect / disconnect
    // ------------------------------------------------------------------

    private JSObject connectionJson() {
        JSObject o = new JSObject();
        o.put("state", adapter == null ? "unavailable" : connectionState);
        o.put("deviceId", connectedId);
        BluetoothDevice d = connectedId == null ? null : seen.get(connectedId);
        String name = null;
        if (d != null) { try { name = d.getName(); } catch (SecurityException ignored) { } }
        o.put("deviceName", name);
        o.put("scanning", scanning);
        o.put("standIn", false);
        o.put("note", adapter == null ? "No Bluetooth adapter on this device." : "");
        return o;
    }

    private void setState(String state) {
        connectionState = state;
        emit("connection.state", f("state", state).put("device", shortId(connectedId)));
        notifyListeners("connectionState", connectionJson());
    }

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt g, int status, int newState) {
            JSObject o = f("device", shortId(connectedId));
            o.put("gattStatus", status);
            o.put("gattStatusName", gattStatusName(status));
            o.put("newState", newState == BluetoothProfile.STATE_CONNECTED ? "connected"
                : newState == BluetoothProfile.STATE_CONNECTING ? "connecting"
                : newState == BluetoothProfile.STATE_DISCONNECTING ? "disconnecting" : "disconnected");
            emit("gatt.connectionStateChange", status == BluetoothGatt.GATT_SUCCESS ? "info" : "error", o);
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                setState("connected");
                try {
                    emit("gatt.requestMtu", f("mtu", 517));
                    g.requestMtu(517);
                    g.discoverServices();
                    emit("gatt.discoverServices.start", new JSObject());
                } catch (SecurityException ignored) { }
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                connectedId = null;
                setState("disconnected");
                failPendingSend("Bike disconnected during the transfer (GATT status " + status + ").");
            }
        }

        @Override
        public void onMtuChanged(BluetoothGatt g, int mtu, int status) {
            // ATT header is 3 bytes; a write payload can use mtu - 3.
            if (status == BluetoothGatt.GATT_SUCCESS && mtu > 23) sendChunkBytes = Math.max(CHUNK_BYTES, mtu - 3);
            JSObject o = f("mtu", mtu);
            o.put("gattStatus", status);
            o.put("chunkBytes", sendChunkBytes);
            emit("gatt.mtuChanged", status == BluetoothGatt.GATT_SUCCESS ? "info" : "warn", o);
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt g, int status) {
            JSArray services = new JSArray();
            int charCount = 0;
            for (BluetoothGattService s : g.getServices()) {
                JSObject so = new JSObject();
                so.put("uuid", s.getUuid().toString());
                so.put("type", s.getType() == BluetoothGattService.SERVICE_TYPE_PRIMARY ? "primary" : "secondary");
                so.put("instanceId", s.getInstanceId());
                JSArray chars = new JSArray();
                for (BluetoothGattCharacteristic c : s.getCharacteristics()) {
                    JSObject co = new JSObject();
                    co.put("uuid", c.getUuid().toString());
                    co.put("instanceId", c.getInstanceId());
                    co.put("properties", propertyNames(c.getProperties()));
                    co.put("propertyMask", c.getProperties());
                    co.put("permissionMask", c.getPermissions());
                    JSArray descriptors = new JSArray();
                    for (BluetoothGattDescriptor de : c.getDescriptors()) {
                        descriptors.put(de.getUuid().toString());
                    }
                    co.put("descriptors", descriptors);
                    chars.put(co);
                    charCount++;
                }
                so.put("characteristics", chars);
                services.put(so);
            }
            JSObject o = new JSObject();
            o.put("deviceId", connectedId);
            o.put("gattStatus", status);
            o.put("services", services);
            JSObject ev = new JSObject();
            ev.put("gattStatus", status);
            ev.put("serviceCount", services.length());
            ev.put("characteristicCount", charCount);
            ev.put("services", services);
            emit("gatt.servicesDiscovered", status == BluetoothGatt.GATT_SUCCESS ? "info" : "error", ev);
            notifyListeners("services", o);
        }

        @Override
        public void onCharacteristicWrite(BluetoothGatt g, BluetoothGattCharacteristic c, int status) {
            if (pendingSend == null) return;
            if (status != BluetoothGatt.GATT_SUCCESS) {
                failPendingSend("Bike rejected a write (GATT status " + status + " " + gattStatusName(status) + ").");
                return;
            }
            JSObject ack = f("offset", sendOffset);
            ack.put("total", sendBuffer.length);
            ack.put("elapsedMs", System.currentTimeMillis() - sendStartedAt);
            emit("gatt.write.ack", ack);
            if (sendOffset >= sendBuffer.length) {
                JSObject o = new JSObject();
                o.put("ok", true);
                o.put("bytes", sendBuffer.length);
                o.put("elapsedMs", System.currentTimeMillis() - sendStartedAt);
                o.put("message", "All " + sendBuffer.length + " GPX bytes were acknowledged by the device. "
                    + "Whether the TFT shows the route depends on the (unverified) bike protocol.");
                emit("transfer.acknowledged", o);
                PluginCall call = pendingSend;
                clearPendingSend();
                call.resolve(o);
                return;
            }
            try { Thread.sleep(CHUNK_DELAY_MS); } catch (InterruptedException ignored) { }
            writeNextChunk();
        }
    };

    private static JSArray propertyNames(int props) {
        List<String> names = new ArrayList<>();
        if ((props & BluetoothGattCharacteristic.PROPERTY_READ) != 0) names.add("read");
        if ((props & BluetoothGattCharacteristic.PROPERTY_WRITE) != 0) names.add("write");
        if ((props & BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE) != 0) names.add("writeNoResponse");
        if ((props & BluetoothGattCharacteristic.PROPERTY_NOTIFY) != 0) names.add("notify");
        if ((props & BluetoothGattCharacteristic.PROPERTY_INDICATE) != 0) names.add("indicate");
        if ((props & BluetoothGattCharacteristic.PROPERTY_BROADCAST) != 0) names.add("broadcast");
        if ((props & BluetoothGattCharacteristic.PROPERTY_SIGNED_WRITE) != 0) names.add("signedWrite");
        if ((props & BluetoothGattCharacteristic.PROPERTY_EXTENDED_PROPS) != 0) names.add("extended");
        JSArray arr = new JSArray();
        for (String n : names) arr.put(n);
        return arr;
    }

    /** The GATT status codes a bike link actually hits, by name. */
    private static String gattStatusName(int status) {
        switch (status) {
            case BluetoothGatt.GATT_SUCCESS: return "SUCCESS";
            case BluetoothGatt.GATT_READ_NOT_PERMITTED: return "READ_NOT_PERMITTED";
            case BluetoothGatt.GATT_WRITE_NOT_PERMITTED: return "WRITE_NOT_PERMITTED";
            case BluetoothGatt.GATT_INSUFFICIENT_AUTHENTICATION: return "INSUFFICIENT_AUTHENTICATION";
            case BluetoothGatt.GATT_INSUFFICIENT_ENCRYPTION: return "INSUFFICIENT_ENCRYPTION";
            case BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED: return "REQUEST_NOT_SUPPORTED";
            case BluetoothGatt.GATT_INVALID_ATTRIBUTE_LENGTH: return "INVALID_ATTRIBUTE_LENGTH";
            case BluetoothGatt.GATT_CONNECTION_CONGESTED: return "CONNECTION_CONGESTED";
            case BluetoothGatt.GATT_FAILURE: return "FAILURE";
            case 8: return "CONNECTION_TIMEOUT";
            case 19: return "TERMINATED_BY_PEER";
            case 22: return "TERMINATED_LOCALLY";
            case 133: return "GATT_ERROR (133 - often out of range or a stale connection)";
            default: return "code " + status;
        }
    }

    @PluginMethod
    public void connect(PluginCall call) {
        String id = call.getString("deviceId");
        if (adapter == null) { call.reject("No Bluetooth adapter on this device.", "NO_ADAPTER"); return; }
        if (id == null) { call.reject("deviceId is required."); return; }
        if (!hasPermissions()) { call.reject("Bluetooth permission not granted.", "NO_PERMISSION"); return; }
        BluetoothDevice d = seen.get(id);
        if (d == null) {
            try { d = adapter.getRemoteDevice(id); } catch (IllegalArgumentException e) {
                call.reject("Unknown device " + id, "UNKNOWN_DEVICE");
                return;
            }
            seen.put(id, d);
        }
        try {
            if (gatt != null) { gatt.close(); }
            connectedId = id;
            sendChunkBytes = CHUNK_BYTES;
            setState("connecting");
            JSObject o = f("device", shortId(id));
            o.put("transport", "LE");
            o.put("bondState", bondName(d.getBondState()));
            emit("gatt.connect", o);
            gatt = d.connectGatt(getContext(), false, gattCallback, BluetoothDevice.TRANSPORT_LE);
        } catch (SecurityException e) {
            connectedId = null;
            setState("disconnected");
            call.reject("Bluetooth permission not granted.", "NO_PERMISSION");
            return;
        }
        call.resolve(connectionJson());
    }

    @PluginMethod
    public void disconnect(PluginCall call) {
        emit("gatt.disconnect", f("device", shortId(connectedId)));
        if (gatt != null) {
            try { gatt.disconnect(); gatt.close(); } catch (SecurityException ignored) { }
            gatt = null;
        }
        connectedId = null;
        if (adapter != null) setState("disconnected");
        failPendingSend("Disconnected by the rider.");
        call.resolve(connectionJson());
    }

    @PluginMethod
    public void getConnectionState(PluginCall call) {
        call.resolve(connectionJson());
    }

    // ------------------------------------------------------------------
    // send route (GPX bytes over a writable characteristic)
    // ------------------------------------------------------------------

    @PluginMethod
    public void sendRoute(PluginCall call) {
        String gpx = call.getString("gpx");
        String serviceUuid = call.getString("serviceUuid");
        String charUuid = call.getString("characteristicUuid");
        if (gpx == null || gpx.isEmpty()) { call.reject("gpx is required."); return; }
        emit("transfer.requested", f("bytes", gpx.length()).put("serviceUuid", serviceUuid)
            .put("characteristicUuid", charUuid));
        if (gatt == null || !"connected".equals(connectionState)) {
            emit("transfer.refused", "warn", f("reason", "NOT_CONNECTED"));
            call.reject("No connected bike; nothing was sent.", "NOT_CONNECTED");
            return;
        }
        if (pendingSend != null) {
            emit("transfer.refused", "warn", f("reason", "BUSY"));
            call.reject("A transfer is already in progress.", "BUSY");
            return;
        }
        if (serviceUuid == null || charUuid == null) {
            emit("transfer.refused", "warn", f("reason", "PROTOCOL_UNVERIFIED"));
            call.reject("The bike's route-transfer GATT service is not verified yet; refusing to send. "
                + "Pass serviceUuid/characteristicUuid once sourced on a real bike.", "PROTOCOL_UNVERIFIED");
            return;
        }
        BluetoothGattService service;
        try { service = gatt.getService(UUID.fromString(serviceUuid)); }
        catch (IllegalArgumentException e) {
            emit("transfer.refused", "warn", f("reason", "BAD_UUID"));
            call.reject("Bad serviceUuid.", "BAD_UUID");
            return;
        }
        BluetoothGattCharacteristic c = service == null ? null : service.getCharacteristic(UUID.fromString(charUuid));
        if (c == null) {
            emit("transfer.refused", "warn", f("reason", "NO_CHARACTERISTIC")
                .put("serviceUuid", serviceUuid).put("characteristicUuid", charUuid));
            call.reject("Connected device does not expose " + serviceUuid + "/" + charUuid
                + "; nothing was sent.", "NO_CHARACTERISTIC");
            return;
        }
        pendingSend = call;
        sendCharacteristic = c;
        sendBuffer = gpx.getBytes(StandardCharsets.UTF_8);
        sendOffset = 0;
        sendStartedAt = System.currentTimeMillis();
        emit("transfer.start", f("bytes", sendBuffer.length).put("chunkBytes", sendChunkBytes)
            .put("properties", propertyNames(c.getProperties())));
        call.setKeepAlive(true);
        writeNextChunk();
    }

    private void writeNextChunk() {
        int end = Math.min(sendBuffer.length, sendOffset + sendChunkBytes);
        byte[] chunk = Arrays.copyOfRange(sendBuffer, sendOffset, end);
        sendOffset = end;
        boolean started;
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                started = gatt.writeCharacteristic(sendCharacteristic, chunk,
                    BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == BluetoothGatt.GATT_SUCCESS;
            } else {
                sendCharacteristic.setValue(chunk);
                started = gatt.writeCharacteristic(sendCharacteristic);
            }
        } catch (SecurityException e) {
            started = false;
        }
        if (!started) failPendingSend("GATT write could not be started at byte " + (sendOffset - chunk.length) + ".");
        else emit("gatt.write", f("offset", sendOffset - chunk.length).put("length", chunk.length)
            .put("total", sendBuffer.length));
    }

    private void failPendingSend(String why) {
        if (pendingSend == null) return;
        emit("transfer.failed", "error", f("reason", why).put("offset", sendOffset)
            .put("total", sendBuffer == null ? 0 : sendBuffer.length));
        PluginCall call = pendingSend;
        clearPendingSend();
        call.reject(why, "TRANSFER_FAILED");
    }

    private void clearPendingSend() {
        if (pendingSend != null) pendingSend.setKeepAlive(false);
        pendingSend = null;
        sendBuffer = null;
        sendOffset = 0;
        sendCharacteristic = null;
    }

    @Override
    protected void handleOnDestroy() {
        if (scanner != null && scanning) { try { scanner.stopScan(scanCallback); } catch (SecurityException ignored) { } }
        if (gatt != null) { try { gatt.close(); } catch (SecurityException ignored) { } }
    }
}
