import { useLocalSearchParams } from "expo-router";

import { PlanView } from "../../components/PlanView";
import { ErrorBox, Screen } from "../../components/ui";
import { useConn, useLoad } from "../../lib/conn";
import { useToast } from "../../lib/toast";

export default function PlanScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { api } = useConn();
  const toast = useToast();
  const plan = useLoad(api && id ? () => api.plan(id) : null, [api, id]);
  return (
    <Screen refreshing={plan.loading} onRefresh={plan.reload}>
      {plan.error ? <ErrorBox text={plan.error} onRetry={plan.reload} /> : null}
      {plan.data && api ? <PlanView key={plan.data.id + plan.data.status} plan={plan.data} api={api} onChange={plan.setData} notify={toast} /> : null}
    </Screen>
  );
}
