import { z } from "zod";

export const createAppSchema = z.object({
  app_name: z
    .string()
    .min(2, { message: "App name must be at least 2 characters long" })
    .regex(/^[a-zA-Z0-9_-]+$/, {
      message:
        "App name can only contain letters, numbers, underscores, and hyphens (no spaces)",
    }),

  deployment_type: z.enum(["manual", "auto"]),

  // Keep these purely optional — no validation here
  public_url: z.string().url(),
  private_url: z.string().url(),
});
