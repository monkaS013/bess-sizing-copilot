"use client";

/**
 * supabase.ts -- Cliente Supabase no browser, com graceful fallback.
 *
 * Se NEXT_PUBLIC_SUPABASE_URL e NEXT_PUBLIC_SUPABASE_ANON_KEY estao
 * configuradas, usa Supabase real (auth.signInAnonymously + persistencia).
 * Caso contrario, retorna stub que gera userId client-side via crypto.UUID
 * -- modo MVP local sem Supabase, funcionalmente equivalente.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

const LOCAL_USER_KEY = "bess.local_user_id";

let _client: SupabaseClient | null = null;

export function isSupabaseConfigured(): boolean {
  return Boolean(URL && ANON);
}

export function getSupabase(): SupabaseClient | null {
  if (!isSupabaseConfigured()) return null;
  if (!_client) {
    _client = createClient(URL!, ANON!, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: false,
      },
    });
  }
  return _client;
}

/**
 * Garante que existe um user identificavel.
 *
 * - Com Supabase configurado: chama signInAnonymously (idempotente -- se ja
 *   ha sessao, reusa). Devolve auth.uid().
 * - Sem Supabase: gera UUID client-side persistido em localStorage
 *   (modo MVP local).
 */
export async function ensureUserId(): Promise<string> {
  const sb = getSupabase();

  if (sb) {
    // Reaproveita sessao existente se houver
    const { data: sessionData } = await sb.auth.getSession();
    if (sessionData.session?.user?.id) {
      return sessionData.session.user.id;
    }
    const { data, error } = await sb.auth.signInAnonymously();
    if (error) {
      console.warn(
        `[supabase] signInAnonymously falhou (${error.message}). ` +
        `Usando UUID local como fallback. Anonymous auth deve estar habilitado em ` +
        `Authentication -> Providers no painel Supabase.`
      );
      return ensureLocalUserId();
    }
    return data.user!.id;
  }

  return ensureLocalUserId();
}

function ensureLocalUserId(): string {
  const cached = localStorage.getItem(LOCAL_USER_KEY);
  if (cached) return cached;
  const uid = (typeof crypto !== "undefined" && "randomUUID" in crypto)
    ? crypto.randomUUID()
    : `local-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  localStorage.setItem(LOCAL_USER_KEY, uid);
  return uid;
}

/**
 * Reset de identidade -- usado em "Nova conversa" se quiser invalidar
 * o user (geralmente nao queremos -- so a sessao). Mantido aqui para
 * uso futuro.
 */
export async function resetUser(): Promise<void> {
  const sb = getSupabase();
  if (sb) await sb.auth.signOut();
  localStorage.removeItem(LOCAL_USER_KEY);
}
