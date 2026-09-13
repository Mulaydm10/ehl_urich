package com.bmwmotorrad.ridefit;

import android.Manifest;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.content.Context;
import android.os.Build;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.LinkedHashMap;
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

    private static final long CHUNK_DELAY_MS = 40;
    private static final int CHUNK_BYTES = 180;

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
    private BluetoothGattCharacteristic sendCharacteristic;

    @Override
    public void load() {
        BluetoothManager mgr = (BluetoothManager) getContext().getSystemService(Context.BLUETOOTH_SERVICE);
        adapter = mgr == null ? null : mgr.getAdapter();
        if (adapter == null) connectionState = "unavailable";
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
        if (hasPermissions()) { call.resolve(permissionsResult()); return; }
        requestPermissionForAlias(needsRuntimeBluetoothPermission() ? "bluetooth" : "location", call, "permissionsCallback");
    }

    @PermissionCallback
    private void permissionsCallback(PluginCall call) {
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
            seen.put(d.getAddress(), d);
            rssi.put(d.getAddress(), result.getRssi());
            notifyListeners("device", deviceJson(d, result.getRssi()));
        }

        @Override
        public void onScanFailed(int errorCode) {
            scanning = false;
            JSObject o = new JSObject();
            o.put("error", "BLE scan failed (code " + errorCode + ")");
            notifyListeners("scanFailed", o);
        }
    };

    private JSObject deviceJson(BluetoothDevice d, Integer signal) {
        JSObject o = new JSObject();
        o.put("id", d.getAddress());
        String name = null;
        try { name = d.getName(); } catch (SecurityException ignored) { /* BLUETOOTH_CONNECT missing */ }
        o.put("name", name == null ? "Unnamed BLE device" : name);
        o.put("rssi", signal);
        boolean bonded = false;
        try { bonded = d.getBondState() == BluetoothDevice.BOND_BONDED; } catch (SecurityException ignored) { }
        o.put("paired", bonded);
        o.put("standIn", false);
        return o;
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
        } catch (SecurityException e) {
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
        call.resolve(o);
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
        notifyListeners("connectionState", connectionJson());
    }

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt g, int status, int newState) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                setState("connected");
                try { g.discoverServices(); } catch (SecurityException ignored) { }
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                connectedId = null;
                setState("disconnected");
                failPendingSend("Bike disconnected during the transfer.");
            }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt g, int status) {
            JSArray services = new JSArray();
            for (BluetoothGattService s : g.getServices()) {
                JSObject so = new JSObject();
                so.put("uuid", s.getUuid().toString());
                JSArray chars = new JSArray();
                for (BluetoothGattCharacteristic c : s.getCharacteristics()) chars.put(c.getUuid().toString());
                so.put("characteristics", chars);
                services.put(so);
            }
            JSObject o = new JSObject();
            o.put("deviceId", connectedId);
            o.put("services", services);
            notifyListeners("services", o);
        }

        @Override
        public void onCharacteristicWrite(BluetoothGatt g, BluetoothGattCharacteristic c, int status) {
            if (pendingSend == null) return;
            if (status != BluetoothGatt.GATT_SUCCESS) {
                failPendingSend("Bike rejected a write (GATT status " + status + ").");
                return;
            }
            if (sendOffset >= sendBuffer.length) {
                JSObject o = new JSObject();
                o.put("ok", true);
                o.put("bytes", sendBuffer.length);
                o.put("message", "All " + sendBuffer.length + " GPX bytes were acknowledged by the device. "
                    + "Whether the TFT shows the route depends on the (unverified) bike protocol.");
                PluginCall call = pendingSend;
                clearPendingSend();
                call.resolve(o);
                return;
            }
            try { Thread.sleep(CHUNK_DELAY_MS); } catch (InterruptedException ignored) { }
            writeNextChunk();
        }
    };

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
            setState("connecting");
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
        if (gatt == null || !"connected".equals(connectionState)) {
            call.reject("No connected bike; nothing was sent.", "NOT_CONNECTED");
            return;
        }
        if (pendingSend != null) { call.reject("A transfer is already in progress.", "BUSY"); return; }
        if (serviceUuid == null || charUuid == null) {
            call.reject("The bike's route-transfer GATT service is not verified yet; refusing to send. "
                + "Pass serviceUuid/characteristicUuid once sourced on a real bike.", "PROTOCOL_UNVERIFIED");
            return;
        }
        BluetoothGattService service;
        try { service = gatt.getService(UUID.fromString(serviceUuid)); }
        catch (IllegalArgumentException e) { call.reject("Bad serviceUuid.", "BAD_UUID"); return; }
        BluetoothGattCharacteristic c = service == null ? null : service.getCharacteristic(UUID.fromString(charUuid));
        if (c == null) {
            call.reject("Connected device does not expose " + serviceUuid + "/" + charUuid
                + "; nothing was sent.", "NO_CHARACTERISTIC");
            return;
        }
        pendingSend = call;
        sendCharacteristic = c;
        sendBuffer = gpx.getBytes(StandardCharsets.UTF_8);
        sendOffset = 0;
        call.setKeepAlive(true);
        writeNextChunk();
    }

    private void writeNextChunk() {
        int end = Math.min(sendBuffer.length, sendOffset + CHUNK_BYTES);
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
    }

    private void failPendingSend(String why) {
        if (pendingSend == null) return;
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
