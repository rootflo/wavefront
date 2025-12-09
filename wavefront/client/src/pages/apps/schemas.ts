import { z } from 'zod';

export const baseAppSchema = z.object({
  app_name: z
    .string()
    .min(2, { message: 'App name must be at least 2 characters long' })
    .regex(/^[a-zA-Z0-9_-]+$/, {
      message: 'App name can only contain letters, numbers, underscores, and hyphens (no spaces)',
    }),

  deployment_type: z.enum(['manual', 'auto']),

  // Keep these purely optional — no validation here
  app_url: z.string().optional(),
  app_secret: z.string().optional(),
  app_key: z.string().optional(),
});

export const createAppSchema = baseAppSchema.superRefine((data, ctx) => {
  if (data.deployment_type === 'manual') {
    // validate app_url
    if (!data.app_url) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'App url is required for manual deployment',
        path: ['app_url'],
      });
    } else {
      // URL validation only if provided
      const urlSchema = z
        .string()
        .url()
        .regex(/^https?:\/\/[^\s/$.?#].[^\s]*$/i);
      const result = urlSchema.safeParse(data.app_url);
      if (!result.success) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Invalid URL format',
          path: ['app_url'],
        });
      }
    }

    // validate secret
    if (!data.app_secret) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'App secret is required for manual deployment',
        path: ['app_secret'],
      });
    }

    // validate key
    if (!data.app_key) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'App key is required for manual deployment',
        path: ['app_key'],
      });
    }
  }
});
