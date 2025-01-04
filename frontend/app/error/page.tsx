'use client';

import { useSearchParams } from 'next/navigation';
import Link from 'next/link';

export default function ErrorPage() {
  const searchParams = useSearchParams();
  const error = searchParams.get('error');

  let errorMessage = 'An error occurred';
  let errorDescription = 'Please try again or contact support if the problem persists.';

  switch (error) {
    case 'AccessDenied':
      errorMessage = 'Access Denied';
      errorDescription = 'You do not have permission to access this resource.';
      break;
    case 'Verification':
      errorMessage = 'Verification Error';
      errorDescription = 'Unable to verify your credentials. Please try signing in again.';
      break;
    case 'OAuthSignin':
      errorMessage = 'Sign In Error';
      errorDescription = 'Error occurred during sign in. Please try again.';
      break;
    case 'OAuthCallback':
      errorMessage = 'Callback Error';
      errorDescription = 'Error occurred during authentication callback. Please try again.';
      break;
    case 'OAuthCreateAccount':
      errorMessage = 'Account Creation Error';
      errorDescription = 'Could not create user account. Please try again.';
      break;
    case 'EmailCreateAccount':
      errorMessage = 'Account Creation Error';
      errorDescription = 'Could not create user account. Please try a different method.';
      break;
    case 'Callback':
      errorMessage = 'Callback Error';
      errorDescription = 'Error occurred during authentication. Please try again.';
      break;
    case 'TokenExpired':
      errorMessage = 'Session Expired';
      errorDescription = 'Your session has expired. Please sign in again.';
      break;
    case 'TokenInvalid':
      errorMessage = 'Invalid Session';
      errorDescription = 'Your session is invalid. Please sign in again.';
      break;
    default:
      if (error) {
        errorMessage = 'Authentication Error';
        errorDescription = error;
      }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="max-w-md w-full space-y-8 p-8 bg-white dark:bg-gray-800 rounded-lg shadow-lg">
        <div className="text-center">
          <h2 className="mt-6 text-3xl font-bold text-gray-900 dark:text-white">
            {errorMessage}
          </h2>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            {errorDescription}
          </p>
        </div>
        <div className="mt-8">
          <Link
            href="/sign-in"
            className="w-full flex justify-center py-3 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-[#5865F2] hover:bg-[#4752C4] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#5865F2] transition-colors duration-200"
          >
            Return to Sign In
          </Link>
        </div>
      </div>
    </div>
  );
} 