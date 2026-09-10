// Cloudflare Email Worker: forward each email to the Juvare dashboard webhook.
//
// Setup:
//   - Create a Worker and paste this file.
//   - Set environment variables:
//       INGEST_TOKEN = shared secret (must match the app's INGEST_TOKEN)
//       WEBHOOK_URL  = https://dashboard.yourdomain/api/ingest
//   - In Email Routing: custom address juvare@yourdomain -> "Send to a Worker".

export default {
  async email(message, env, ctx) {
    const init = {
      method: "POST",
      headers: {
        "content-type": "message/rfc822",
        "x-ingest-token": env.INGEST_TOKEN,
        // Raw email body needs full-text; new Workers email APIs may vary.
        "x-mail-subject": message.title || "",
        "x-original-from": message.from || "",
      },
      body: message.raw,
    };
    ctx.waitUntil(fetch(env.WEBHOOK_URL, init));
  },
};