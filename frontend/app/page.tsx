import { redirect } from "next/navigation";

/* A home agora é a tela "Monitorar" (a Central). O antigo Dashboard — que
   misturava win-back de cancelados e induzia leitura errada dos números —
   foi PRESERVADO em /dashboard (nenhum código apagado), apenas tirado do
   caminho. Quem abre o painel cai direto na visão simples e honesta. */
export default function Home() {
  redirect("/central");
}
