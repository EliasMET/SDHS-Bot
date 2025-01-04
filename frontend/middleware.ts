import { withAuth } from 'next-auth/middleware';
import { NextResponse } from 'next/server';

export default withAuth(
  function middleware(req) {
    // If the user is not authenticated and trying to access a protected route
    if (!req.nextauth.token && !req.nextUrl.pathname.startsWith('/sign-in')) {
      return NextResponse.redirect(new URL('/sign-in', req.url));
    }

    // If the user is authenticated and trying to access sign-in page
    if (req.nextauth.token && req.nextUrl.pathname.startsWith('/sign-in')) {
      return NextResponse.redirect(new URL('/', req.url));
    }

    return NextResponse.next();
  },
  {
    callbacks: {
      authorized: ({ token }) => {
        return !!token;
      },
    },
  }
);

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico|discord-mark-.*).*)'],
}; 