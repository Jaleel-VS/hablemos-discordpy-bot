// Discord Embedded App SDK handshake.
//
// Flow (per https://docs.discord.com/developers/activities/building-an-activity):
//   1. new DiscordSDK(CLIENT_ID) and await ready()
//   2. authorize({ scope: ["identify"] }) -> { code }
//   3. POST code to our backend /.proxy/api/token -> { access_token }
//   4. authenticate({ access_token }) so the SDK is authenticated
//   5. verify identity server-side via /.proxy/api/me (never trust the client)
//
// Every backend call goes through the `/.proxy` prefix so it survives
// Discord's CSP-restricted proxy. The proxy strips `/.proxy` before the
// request reaches FastAPI.
import { DiscordSDK } from "@discord/embedded-app-sdk";

const CLIENT_ID = import.meta.env.VITE_DISCORD_CLIENT_ID as string | undefined;

export interface DiscordUser {
  id: string;
  username: string;
  global_name: string;
  avatar: string;
}

export interface Session {
  sdk: DiscordSDK;
  user: DiscordUser;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(`Request to ${path} failed with ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export async function startSession(): Promise<Session> {
  if (!CLIENT_ID) {
    throw new Error("VITE_DISCORD_CLIENT_ID is not set at build time");
  }

  const sdk = new DiscordSDK(CLIENT_ID);
  await sdk.ready();

  // Step 2: get an authorization code scoped to identify.
  const { code } = await sdk.commands.authorize({
    client_id: CLIENT_ID,
    response_type: "code",
    state: "",
    prompt: "none",
    scope: ["identify"],
  });

  // Step 3: exchange the code for an access token, server-side.
  const { access_token } = await postJson<{ access_token: string }>(
    "/.proxy/api/token",
    { code },
  );

  // Step 4: authenticate the SDK with the token.
  await sdk.commands.authenticate({ access_token });

  // Step 5: resolve the *verified* identity from our backend.
  const user = await postJson<DiscordUser>("/.proxy/api/me", {
    access_token,
  });

  return { sdk, user };
}
