export type SupportedLocale = 'en' | 'am';

const english = {
  account: 'Account',
  signedOut: 'Sign in to continue securely.',
  authenticated: 'You are signed in.',
  restoring: 'Restoring your secure session…',
  email: 'Email',
  phone: 'Phone',
  contact: 'Email or phone number',
  password: 'Password',
  signIn: 'Sign in',
  register: 'Create account',
  switchToRegister: 'Create a new account',
  switchToSignIn: 'Use an existing account',
  verificationRequired: 'Verify your contact before using protected AYO services.',
  sendCode: 'Send verification code',
  verificationCode: 'Six-digit verification code',
  verify: 'Verify contact',
  changeLanguage: 'Change language',
  back: 'Back',
  signOut: 'Sign out',
  retry: 'Try again',
  temporaryFailure: 'AYO is temporarily unavailable. Please try again.',
  sessionExpired: 'Your session ended. Please sign in again.',
  secureStorageUnavailable: 'Secure sign-in is unavailable on this device.',
  malformedResponse: 'AYO returned an unsupported response. Please try again later.',
  preProduction: 'PRE-PRODUCTION',
} as const;

type AuthenticationStrings = { readonly [K in keyof typeof english]: string };

const amharic: AuthenticationStrings = {
  account: 'መለያ',
  signedOut: 'በደህንነት ለመቀጠል ይግቡ።',
  authenticated: 'ገብተዋል።',
  restoring: 'የተጠበቀው ክፍለ ጊዜዎ እየተመለሰ ነው…',
  email: 'ኢሜይል',
  phone: 'ስልክ',
  contact: 'ኢሜይል ወይም ስልክ ቁጥር',
  password: 'የይለፍ ቃል',
  signIn: 'ይግቡ',
  register: 'መለያ ይፍጠሩ',
  switchToRegister: 'አዲስ መለያ ይፍጠሩ',
  switchToSignIn: 'ያለዎትን መለያ ይጠቀሙ',
  verificationRequired: 'የተጠበቁ የAYO አገልግሎቶችን ከመጠቀምዎ በፊት መገኛዎን ያረጋግጡ።',
  sendCode: 'የማረጋገጫ ኮድ ይላኩ',
  verificationCode: 'ባለስድስት አሃዝ የማረጋገጫ ኮድ',
  verify: 'መገኛውን ያረጋግጡ',
  changeLanguage: 'ቋንቋ ይቀይሩ',
  back: 'ተመለስ',
  signOut: 'ይውጡ',
  retry: 'እንደገና ይሞክሩ',
  temporaryFailure: 'AYO ለጊዜው አይገኝም። እንደገና ይሞክሩ።',
  sessionExpired: 'ክፍለ ጊዜዎ አብቅቷል። እንደገና ይግቡ።',
  secureStorageUnavailable: 'በዚህ መሣሪያ ላይ የተጠበቀ መግቢያ አይገኝም።',
  malformedResponse: 'AYO ያልተደገፈ ምላሽ ሰጥቷል። ቆይተው ይሞክሩ።',
  preProduction: 'ቅድመ-ምርት',
};

export const authenticationCopy: Readonly<Record<SupportedLocale, AuthenticationStrings>> = {
  en: english,
  am: amharic,
};
