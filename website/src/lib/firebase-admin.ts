import { initializeApp, getApps, cert, type App } from 'firebase-admin/app';
import { getAuth } from 'firebase-admin/auth';

let app: App;

if (getApps().length === 0) {
  // In development without a service account, use project ID only.
  // Firebase Admin can verify ID tokens with just the project ID
  // by fetching Google's public keys.
  app = initializeApp({
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  });
} else {
  app = getApps()[0];
}

export const adminAuth = getAuth(app);

export interface VerifiedUser {
  uid: string;
  email?: string;
  name?: string;
}

export async function verifyRequest(request: Request): Promise<VerifiedUser> {
  const authHeader = request.headers.get('authorization');
  if (!authHeader?.startsWith('Bearer ')) {
    throw new Error('Missing or invalid Authorization header');
  }

  const token = authHeader.slice(7);
  const decoded = await adminAuth.verifyIdToken(token);

  return {
    uid: decoded.uid,
    email: decoded.email,
    name: decoded.name,
  };
}
