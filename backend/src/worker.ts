import { Container, getContainer } from "@cloudflare/containers";

interface Env {
  BACKEND: DurableObjectNamespace<Backend>;
  SUPABASE_URL: string;
  SUPABASE_SERVICE_ROLE_KEY: string;
  LIVE_CV_BUS_ID?: string;
  ALLOWED_ORIGINS?: string;
}

// Satu instance FastAPI: state graf/jadwal dan MQTT live ada di memory proses,
// jadi semua request harus ke container yang sama (max_instances = 1).
export class Backend extends Container<Env> {
  defaultPort = 8000;
  sleepAfter = "2h";

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.envVars = {
      SUPABASE_URL: env.SUPABASE_URL,
      SUPABASE_SERVICE_ROLE_KEY: env.SUPABASE_SERVICE_ROLE_KEY,
      LIVE_CV_BUS_ID: env.LIVE_CV_BUS_ID ?? "",
      ALLOWED_ORIGINS: env.ALLOWED_ORIGINS ?? "http://localhost:3000",
    };
  }
}

export default {
  fetch(request: Request, env: Env) {
    return getContainer(env.BACKEND).fetch(request);
  },
};
