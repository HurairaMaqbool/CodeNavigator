import { redirect } from "next/navigation";

/** Backward-compatible alias — chat lives at /chat now. */
export default function WorkspacePage() {
  redirect("/chat");
}
