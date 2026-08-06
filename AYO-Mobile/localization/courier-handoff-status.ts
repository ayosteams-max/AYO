import type { SupportedLocale } from './authentication';
import type { HandoffStatusCategory } from '@/domain/courier-handoff-status';

const english = {
  title: 'Handoff status', preProduction: 'PRE-PRODUCTION', loading: 'Checking current handoff status…',
  stale: 'Information may be out of date', unavailable: 'Unable to confirm current status', malformed: 'AYO could not safely read this status.', conflicting: 'Current handoff information does not agree.',
  refresh: 'Refresh', refreshing: 'Refreshing…', account: 'Account', returnAreas: 'Return to operating areas',
  pickup_current: 'Pickup work is current', travelling: 'Travelling to the merchant', at_merchant: 'At the merchant', waiting_for_merchant: 'Waiting for merchant', ready_for_handoff: 'Ready for handoff', handoff_in_progress: 'Handoff in progress', pickup_confirmed: 'Pickup confirmed', pickup_ended: 'This pickup is no longer current',
  guidance_refresh: 'Refresh to confirm the latest status.', guidance_wait: 'Wait for the merchant to prepare the handoff.', guidance_ready: 'The handoff is ready. Follow the approved in-person process.', guidance_progress: 'The handoff is being confirmed.', guidance_confirmed: 'The handoff has been confirmed.', guidance_ended: 'Return to your operating areas for current work.',
} as const;
type Strings = { readonly [K in keyof typeof english]: string };
const amharic: Strings = {
  title: 'የርክክብ ሁኔታ', preProduction: 'ቅድመ-ምርት', loading: 'የአሁኑ የርክክብ ሁኔታ እየተረጋገጠ ነው…',
  stale: 'መረጃው ያረጀ ሊሆን ይችላል', unavailable: 'የአሁኑን ሁኔታ ማረጋገጥ አልተቻለም', malformed: 'AYO ይህን ሁኔታ በደህና ማንበብ አልቻለም።', conflicting: 'የአሁኑ የርክክብ መረጃ አይጣጣምም።',
  refresh: 'አድስ', refreshing: 'እየታደሰ ነው…', account: 'መለያ', returnAreas: 'ወደ የስራ ክፍሎች ተመለስ',
  pickup_current: 'የማንሳት ስራው አሁንም የአሁኑ ነው', travelling: 'ወደ ነጋዴው በመጓዝ ላይ', at_merchant: 'ነጋዴው ቦታ ደርሷል', waiting_for_merchant: 'ነጋዴውን በመጠበቅ ላይ', ready_for_handoff: 'ለርክክብ ዝግጁ ነው', handoff_in_progress: 'ርክክቡ በሂደት ላይ ነው', pickup_confirmed: 'ማንሳቱ ተረጋግጧል', pickup_ended: 'ይህ የማንሳት ስራ ከእንግዲህ የአሁኑ አይደለም',
  guidance_refresh: 'የቅርብ ጊዜውን ሁኔታ ለማረጋገጥ ያድሱ።', guidance_wait: 'ነጋዴው ርክክቡን እስኪያዘጋጅ ይጠብቁ።', guidance_ready: 'ርክክቡ ዝግጁ ነው። የተፈቀደውን የአካል ርክክብ ሂደት ይከተሉ።', guidance_progress: 'ርክክቡ እየተረጋገጠ ነው።', guidance_confirmed: 'ርክክቡ ተረጋግጧል።', guidance_ended: 'የአሁኑን ስራ ለማየት ወደ የስራ ክፍሎችዎ ይመለሱ።',
};
export const courierHandoffCopy: Readonly<Record<SupportedLocale, Strings>> = { en: english, am: amharic };
export function guidanceKey(status: HandoffStatusCategory): keyof Strings {
  if (status === 'waiting_for_merchant') return 'guidance_wait';
  if (status === 'ready_for_handoff') return 'guidance_ready';
  if (status === 'handoff_in_progress') return 'guidance_progress';
  if (status === 'pickup_confirmed') return 'guidance_confirmed';
  if (status === 'pickup_ended') return 'guidance_ended';
  return 'guidance_refresh';
}
