"use client";

import { useEffect, useState } from "react";
import { getNotificationSettings, saveNotificationSettings, testNotifications } from "@/lib/api";

export default function SettingsPage() {
  const [form, setForm] = useState({ email: "", resend_api_key: "", resend_from_email: "",
    telegram_bot_token: "", telegram_chat_id: "", email_enabled: false, telegram_enabled: false });
  const [secretState, setSecretState] = useState({ resend: false, telegram: false });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { getNotificationSettings().then((data) => {
    setForm((current) => ({ ...current, email: data.email, resend_from_email: data.resend_from_email,
      telegram_chat_id: data.telegram_chat_id, email_enabled: data.email_enabled,
      telegram_enabled: data.telegram_enabled }));
    setSecretState({ resend: data.has_resend_api_key, telegram: data.has_telegram_bot_token });
  }).catch(() => setMessage("Ayarlar yüklenemedi.")); }, []);

  const set = (key: keyof typeof form, value: string | boolean) => setForm((current) => ({ ...current, [key]: value }));
  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setMessage("");
    try {
      const result = await saveNotificationSettings(form);
      setSecretState({ resend: result.has_resend_api_key, telegram: result.has_telegram_bot_token });
      setForm((current) => ({ ...current, resend_api_key: "", telegram_bot_token: "" }));
      setMessage("Bildirim ayarları kaydedildi.");
    } catch { setMessage("Ayarlar kaydedilemedi."); } finally { setBusy(false); }
  }
  async function test() {
    setBusy(true); setMessage("");
    try { const result = await testNotifications();
      setMessage(result.status === "sent" ? `Test bildirimi gönderildi: ${result.channels.join(", ")}` : `Gönderilemedi: ${result.errors.join(" · ")}`);
    } catch { setMessage("Test bildirimi gönderilemedi."); } finally { setBusy(false); }
  }

  return <div>
    <h1>Bildirim Ayarları</h1>
    <p className="lead">Portföy ve takip listesi uyarılarının teslim kanallarını yapılandırın. Gizli anahtarlar kaydedildikten sonra tekrar gösterilmez.</p>
    <form className="card settings-form" onSubmit={save}>
      <h2>E-posta · Resend</h2>
      <label className="check-row"><input type="checkbox" checked={form.email_enabled} onChange={(e) => set("email_enabled", e.target.checked)} /> E-posta bildirimlerini etkinleştir</label>
      <div className="grid-2">
        <label className="field">Alıcı e-posta<input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} placeholder="kullanici@example.com" /></label>
        <label className="field">Gönderen e-posta<input value={form.resend_from_email} onChange={(e) => set("resend_from_email", e.target.value)} placeholder="Bildirim <alerts@domain.com>" /></label>
        <label className="field">Resend API anahtarı<input type="password" value={form.resend_api_key} onChange={(e) => set("resend_api_key", e.target.value)} placeholder={secretState.resend ? "Kayıtlı · değiştirmek için yeni değer girin" : "re_..."} autoComplete="new-password" /></label>
      </div>
      <h2>Telegram</h2>
      <label className="check-row"><input type="checkbox" checked={form.telegram_enabled} onChange={(e) => set("telegram_enabled", e.target.checked)} /> Telegram bildirimlerini etkinleştir</label>
      <div className="grid-2">
        <label className="field">Bot token<input type="password" value={form.telegram_bot_token} onChange={(e) => set("telegram_bot_token", e.target.value)} placeholder={secretState.telegram ? "Kayıtlı · değiştirmek için yeni değer girin" : "123456:ABC..."} autoComplete="new-password" /></label>
        <label className="field">Chat ID<input value={form.telegram_chat_id} onChange={(e) => set("telegram_chat_id", e.target.value)} placeholder="123456789" /></label>
      </div>
      <div className="form-row"><button className="btn primary" disabled={busy}>Kaydet</button><button type="button" className="btn" onClick={test} disabled={busy}>Test bildirimi gönder</button></div>
      {message && <p className="note" role="status">{message}</p>}
    </form>
  </div>;
}
