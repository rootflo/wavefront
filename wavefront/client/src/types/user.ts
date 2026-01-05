export interface IUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
}

import { emailRegex, passwordRegex } from '@app/utils/regex';
import { z } from 'zod';

export const createUserSchema = z.object({
  email: z.string().min(1, 'Email is required').regex(emailRegex, 'Invalid email format'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(passwordRegex, 'Password must contain uppercase, lowercase, number, and special character'),
  first_name: z.string().min(1, 'First name is required').max(100, 'First name must be 100 characters or less'),
  last_name: z.string().min(1, 'Last name is required').max(100, 'Last name must be 100 characters or less'),
});

export const updateUserSchema = z.object({
  email: z.string().regex(emailRegex, 'Invalid email format').optional().or(z.literal('')),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(passwordRegex, 'Password must contain uppercase, lowercase, number, and special character')
    .optional()
    .or(z.literal('')),
  first_name: z
    .string()
    .min(1, 'First name is required')
    .max(100, 'First name must be 100 characters or less')
    .optional()
    .or(z.literal('')),
  last_name: z
    .string()
    .min(1, 'Last name is required')
    .max(100, 'Last name must be 100 characters or less')
    .optional()
    .or(z.literal('')),
});

export type CreateUserInput = z.infer<typeof createUserSchema>;
export type UpdateUserInput = z.infer<typeof updateUserSchema>;
