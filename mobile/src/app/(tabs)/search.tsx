import { useState } from "react";
import { Text, TextInput, View } from "react-native";

import { Btn, Card, H1, Screen, s } from "../../components/ui";
import { Hit, human } from "../../lib/api";
import { useConn } from "../../lib/conn";
import { C } from "../../lib/theme";

/** Find a file on the PC by what is inside it: "dubai invoice march", "contract pdf 2026". */
export default function Search() {
  const { api } = useConn();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function go() {
    if (!api || !q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setHits(await api.search(q.trim()));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <H1 sub="Searches inside your documents on the PC — words, file type and month or year.">Search</H1>
      <Card>
        <TextInput
          value={q}
          onChangeText={setQ}
          onSubmitEditing={go}
          returnKeyType="search"
          placeholder="e.g. dubai invoice march"
          placeholderTextColor={C.muted}
          autoCapitalize="none"
          accessibilityLabel="Search files"
          style={{ backgroundColor: C.panel2, color: C.text, borderRadius: 10, borderWidth: 1, borderColor: C.line, padding: 12, marginBottom: 12, fontSize: 15 }}
        />
        <Btn label="Search" busy={busy} onPress={go} />
      </Card>
      {error ? <Text style={{ color: C.bad }}>{error}</Text> : null}
      {hits ? (
        <Card title={hits.length ? `${hits.length} found` : "Nothing found"}>
          {hits.length === 0 ? <Text style={s.muted}>Try fewer words, or refresh the index on the PC (Search page).</Text> : null}
          {hits.map((h) => (
            <View key={h.path} style={{ paddingVertical: 10, borderTopWidth: 1, borderTopColor: C.line, gap: 3 }}>
              <Text style={[s.text, { fontWeight: "600" }]}>{h.name}</Text>
              <Text style={[s.muted, { fontSize: 12 }]} numberOfLines={2}>{h.path}</Text>
              {h.snippet ? <Text style={s.muted} numberOfLines={3}>{h.snippet.replace(/[[\]]/g, "")}</Text> : null}
              <Text style={[s.muted, { fontSize: 12 }]}>{human(h.size)} · {new Date(h.mtime * 1000).toLocaleDateString()}</Text>
            </View>
          ))}
        </Card>
      ) : null}
    </Screen>
  );
}
