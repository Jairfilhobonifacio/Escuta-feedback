import { redirect } from "next/navigation";

/* A tela "Mapeamento" mudou de rota: /temas -> /mapeamento. Este redirect mantém
   bookmarks/links antigos funcionando (transparente para o usuário). */
export default function TemasRedirect() {
  redirect("/mapeamento");
}
