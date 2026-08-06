import type { SupportedLocale } from './authentication';

const english = {
  personal: 'Personal', myBusiness: 'My business', deliveries: 'Deliveries', currentPickup: 'Current pickup',
  switchArea: 'Switch area', available: 'Available', pending: 'Pending review', suspended: 'Suspended',
  refresh: 'Refresh', refreshing: 'Refreshing…', unable: 'Unable to load your areas', stale: 'Information may be out of date',
  empty: 'No available area', emptyHelp: 'Your account is secure, but no operating area is available right now.',
  choose: 'Choose an area', chooseHelp: 'Only areas confirmed by AYO are shown.', account: 'Account', signOut: 'Sign out',
  preProduction: 'PRE-PRODUCTION', businessSoon: 'Business order views will be available in a later pre-production update.',
  pickupSoon: 'Your current work is confirmed. Pickup status will be available in a later pre-production update.',
  pendingHelp: 'This business is still under review.', suspendedHelp: 'This business area is currently unavailable.',
  loading: 'Loading your available areas…', malformed: 'AYO could not safely read the available areas. Please try again later.',
} as const;

type OperationalShellStrings = { readonly [K in keyof typeof english]: string };

const amharic: OperationalShellStrings = {
  personal: 'የግል', myBusiness: 'የእኔ ንግድ', deliveries: 'ማድረሻዎች', currentPickup: 'የአሁኑ ማንሳት',
  switchArea: 'ክፍል ይቀይሩ', available: 'ዝግጁ', pending: 'በግምገማ ላይ', suspended: 'ለጊዜው ታግዷል',
  refresh: 'አድስ', refreshing: 'እየታደሰ ነው…', unable: 'ያሉትን ክፍሎች መጫን አልተቻለም', stale: 'መረጃው ያረጀ ሊሆን ይችላል',
  empty: 'አሁን የሚገኝ ክፍል የለም', emptyHelp: 'መለያዎ የተጠበቀ ነው፤ አሁን ግን የሚገኝ የስራ ክፍል የለም።',
  choose: 'ክፍል ይምረጡ', chooseHelp: 'በAYO የተረጋገጡ ክፍሎች ብቻ ይታያሉ።', account: 'መለያ', signOut: 'ውጣ',
  preProduction: 'ቅድመ-ምርት', businessSoon: 'የንግድ ትዕዛዝ እይታ በቀጣይ የቅድመ-ምርት ማሻሻያ ይቀርባል።',
  pickupSoon: 'የአሁኑ ስራዎ ተረጋግጧል። የማንሳት ሁኔታ በቀጣይ የቅድመ-ምርት ማሻሻያ ይቀርባል።',
  pendingHelp: 'ይህ ንግድ አሁንም በግምገማ ላይ ነው።', suspendedHelp: 'ይህ የንግድ ክፍል ለጊዜው አይገኝም።',
  loading: 'ያሉዎት ክፍሎች እየተጫኑ ነው…', malformed: 'AYO ያሉትን ክፍሎች በደህና ማንበብ አልቻለም። ቆይተው ይሞክሩ።',
};

export const operationalShellCopy: Readonly<Record<SupportedLocale, OperationalShellStrings>> = { en: english, am: amharic };
