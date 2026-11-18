import { CameraView, useCameraPermissions } from "expo-camera";
import * as Device from "expo-device";
import * as Network from "expo-network";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Platform, Text, TextInput, View } from "react-native";

import { Btn, Card, H1, Screen, s } from "../components/ui";
import { claimPin, client, Conn, discoverPCs, FoundPC, parsePairing } from "../lib/api";
import { useConn } from "../lib/conn";
import { C } from "../lib/theme";

export default function Pair() {
  const { connect } = useConn();
  // Scanning the QR with the phone's own camera opens drivemind://pair?host=..&token=.. right here.
  const params = useLocalSearchParams<{ host?: string; port?: string; token?: string; id?: string }>();
  const [permission, requestPermission] = useCameraPermissions();
  const [scanning, setScanning] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const handled = useRef(false);
  const [looking, setLooking] = useState(false);
  const [lookedOnce, setLookedOnce] = useState(false);
  const [pcs, setPcs] = useState<FoundPC[]>([]);
  const [chosen, setChosen] = useState<FoundPC | null>(null);
  const [pin, setPin] = useState("");

  async function findPCs() {
    setLooking(true);
    setError(null);
    setPcs([]);
    setChosen(null);
    try {
      const ip = await Network.getIpAddressAsync();
      const all = await discoverPCs(ip, 7878, (pc) => setPcs((l) => [...l, pc]));
      if (all.length === 1) setChosen(all[0]);
      if (!all.length)
        setError("No PC found. On the PC press “Pair a phone” first (that turns on Wi-Fi sync), and keep both on the same Wi-Fi.");
    } catch {
      setError("Couldn't read this phone's Wi-Fi address. Scan the QR code instead.");
    } finally {
      setLooking(false);
      setLookedOnce(true);
    }
  }

  async function pairWithPin() {
    if (!chosen) return;
    setBusy(true);
    setError(null);
    try {
      const name = Device.deviceName || Device.modelName || "Android phone";
      const c = await claimPin(chosen.host, chosen.port, pin, name);
      await connect(c);
      router.replace("/");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function tryPair(c: Conn | null) {
    if (!c) {
      setError("That code doesn't look right. It should look like 192.168.1.5:7878#abc… (shown on your PC).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const hello = await client(c).hello();
      await connect({ ...c, pc: hello.pc });
      router.replace("/");
    } catch (e) {
      setError((e as Error).message);
      handled.current = false;
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (params.host && params.token && !handled.current) {
      handled.current = true;
      tryPair({ host: params.host, port: Number(params.port || 7878), token: params.token, id: params.id });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.host, params.token]);

  return (
    <Screen>
      <H1 sub="On your PC open DriveMind > Settings > Phone > Pair a phone. Your phone must be on the same Wi-Fi.">Connect to your PC</H1>

      <Card title="Find my PC">
        <Text style={[s.muted, { marginBottom: 12 }]}>
          DriveMind looks for your PC on this Wi-Fi. Then type the 6-digit code your PC shows.
        </Text>
        {pcs.map((pc) => (
          <Btn
            key={pc.host}
            kind={chosen?.host === pc.host ? "primary" : "ghost"}
            label={`${pc.pc} · ${pc.host}${pc.pairing_open ? "" : " (press Pair a phone on it)"}`}
            onPress={() => setChosen(pc)}
          />
        ))}
        {chosen ? (
          <View style={{ marginTop: 8 }}>
            <TextInput
              value={pin}
              onChangeText={(t) => setPin(t.replace(/\D/g, "").slice(0, 6))}
              placeholder="6-digit code"
              placeholderTextColor={C.muted}
              keyboardType="number-pad"
              maxLength={6}
              accessibilityLabel="6-digit pairing code"
              style={{ backgroundColor: C.panel2, color: C.text, borderRadius: 10, borderWidth: 1, borderColor: C.line,
                padding: 12, fontSize: 24, letterSpacing: 8, textAlign: "center", marginBottom: 12 }}
            />
            <Btn label={`Pair with ${chosen.pc}`} busy={busy} disabled={pin.length !== 6} onPress={pairWithPin} />
          </View>
        ) : (
          <Btn label={looking ? "Looking on your Wi-Fi…" : lookedOnce ? "Look again" : "Find my PC"} busy={looking} onPress={findPCs} />
        )}
      </Card>

      {scanning && permission?.granted ? (
        <Card title="Point at the QR code">
          <View style={{ height: 320, borderRadius: 12, overflow: "hidden", marginBottom: 12 }}>
            <CameraView
              style={{ flex: 1 }}
              barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
              onBarcodeScanned={({ data }) => {
                if (handled.current) return;
                handled.current = true;
                setScanning(false);
                tryPair(parsePairing(data));
              }}
            />
          </View>
          <Btn label="Cancel" kind="ghost" onPress={() => setScanning(false)} />
        </Card>
      ) : (
        <Card title="Or scan the QR code">
          <Text style={[s.muted, { marginBottom: 12 }]}>Fastest way: scan the code shown on your PC.</Text>
          <Btn
            label={Platform.OS === "web" ? "Camera not available here" : "Scan code"}
            disabled={Platform.OS === "web"}
            busy={busy && !code}
            onPress={async () => {
              const p = permission?.granted ? permission : await requestPermission();
              if (p.granted) {
                handled.current = false;
                setScanning(true);
              } else setError("Camera permission is needed to scan. You can type the code instead.");
            }}
          />
        </Card>
      )}

      <Card title="Or enter the code">
        <TextInput
          value={code}
          onChangeText={setCode}
          placeholder="192.168.1.5:7878#…"
          placeholderTextColor={C.muted}
          autoCapitalize="none"
          autoCorrect={false}
          accessibilityLabel="Pairing code"
          style={{ backgroundColor: C.panel2, color: C.text, borderRadius: 10, borderWidth: 1, borderColor: C.line, padding: 12, fontFamily: "monospace", marginBottom: 12 }}
        />
        <Btn label="Connect" busy={busy && !!code} onPress={() => tryPair(parsePairing(code))} />
      </Card>

      {error ? <Text style={{ color: C.bad, marginTop: 4 }}>{error}</Text> : null}
    </Screen>
  );
}
