import { router } from "expo-router";
import { useRef, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, type ScrollViewInstance, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { H1, s } from "../../components/ui";
import { ChatAnswer } from "../../lib/api";
import { useConn } from "../../lib/conn";
import { C } from "../../lib/theme";

type Msg = { role: "user" | "assistant"; text: string; answer?: ChatAnswer };

const STARTERS = ["What is eating my space?", "C drive saaf karo", "Find my Dubai invoice", "Is my SSD healthy?"];
// Assistant actions name dashboard pages; these are the phone screens that do the same job.
const PHONE_TARGET: Record<string, string> = { caches: "/cleaner", temp: "/cleaner", home: "/", more: "/plans", apps: "/" };

/** Ask DriveMind: the same assistant as the PC dashboard, answered by your PC from its own data. */
export default function Ask() {
  const { api } = useConn();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const scroll = useRef<ScrollViewInstance>(null);

  async function ask(q: string) {
    q = q.trim();
    if (!q || !api || busy) return;
    setText("");
    const history = msgs.slice(-6).map((m) => ({ role: m.role, content: m.text }));
    setMsgs((l) => [...l, { role: "user", text: q }]);
    setBusy(true);
    try {
      const a = await api.chat(q, history);
      setMsgs((l) => [...l, { role: "assistant", text: a.answer, answer: a }]);
    } catch (e) {
      setMsgs((l) => [...l, { role: "assistant", text: (e as Error).message }]);
    } finally {
      setBusy(false);
      setTimeout(() => scroll.current?.scrollToEnd({ animated: true }), 50);
    }
  }

  return (
    <SafeAreaView style={s.screen} edges={["top", "left", "right"]}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView ref={scroll} contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
          <H1 sub="English or Roman Urdu. Answers come from your PC; nothing leaves your home.">Ask DriveMind</H1>
          {msgs.length === 0 ? (
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              {STARTERS.map((q) => (
                <Pressable key={q} onPress={() => ask(q)} accessibilityRole="button" style={chip()}>
                  <Text style={{ color: C.text }}>{q}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}
          {msgs.map((m, i) => (
            <View key={i} style={m.role === "user" ? userBubble() : botBubble()}>
              <Text style={{ color: m.role === "user" ? C.accentInk : C.text, fontSize: 15, lineHeight: 21 }}>{m.text}</Text>
              {m.answer?.ai && m.answer.sources.length ? ( /* plain answers already list the files */
                <View style={{ marginTop: 8, gap: 4 }}>
                  {m.answer.sources.map((src, j) => (
                    <Text key={src.path} style={s.muted} numberOfLines={2}>[{j + 1}] {src.name}</Text>
                  ))}
                </View>
              ) : null}
              {m.answer?.actions.length ? (
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                  {m.answer.actions.map((a) => (
                    <Pressable key={a.label} accessibilityRole="button" style={chip()}
                      onPress={() => router.push((PHONE_TARGET[a.target] || "/") as never)}>
                      <Text style={{ color: C.accent }}>{a.label}</Text>
                    </Pressable>
                  ))}
                </View>
              ) : null}
              {m.answer ? (
                <Text style={[s.muted, { marginTop: 6, fontSize: 11 }]}>
                  {m.answer.ai ? "Written by your local AI from DriveMind's facts" : "From DriveMind's own data"}
                </Text>
              ) : null}
            </View>
          ))}
          {busy ? <Text style={[s.muted, { marginTop: 4 }]}>Your PC is thinking…</Text> : null}
        </ScrollView>
        <View style={{ flexDirection: "row", gap: 8, padding: 12, borderTopWidth: 1, borderTopColor: C.line, backgroundColor: C.panel }}>
          <TextInput
            value={text}
            onChangeText={setText}
            onSubmitEditing={() => ask(text)}
            placeholder="Ask about your files or drive"
            placeholderTextColor={C.muted}
            returnKeyType="send"
            accessibilityLabel="Question for DriveMind"
            style={{ flex: 1, backgroundColor: C.panel2, color: C.text, borderRadius: 10, borderWidth: 1, borderColor: C.line, paddingHorizontal: 12, minHeight: 46 }}
          />
          <Pressable accessibilityRole="button" accessibilityLabel="Send" onPress={() => ask(text)} disabled={busy || !text.trim()}
            style={[s.btn, { opacity: busy || !text.trim() ? 0.5 : 1 }]}>
            <Text style={s.btnText}>Send</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const chip = () => ({ borderWidth: 1, borderColor: C.line, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: C.panel });
const userBubble = () => ({ alignSelf: "flex-end" as const, backgroundColor: C.accent, borderRadius: 14, padding: 12, marginVertical: 6, maxWidth: "85%" as const });
const botBubble = () => ({ alignSelf: "flex-start" as const, backgroundColor: C.panel, borderColor: C.line, borderWidth: 1, borderRadius: 14, padding: 12, marginVertical: 6, maxWidth: "92%" as const });
