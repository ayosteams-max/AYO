import type { SupportedLocale } from './authentication';

const english = {
  heading: 'Operational orders', help: 'Select an order to view its courier pickup status.', refresh: 'Refresh orders', refreshing: 'Refreshing orders…',
  loading: 'Loading your orders…', empty: 'No orders are available right now.', unavailable: 'Orders are temporarily unavailable.', authorityLost: 'This merchant area is no longer available.', malformed: 'AYO could not safely read these orders.', stale: 'Showing earlier order information while the connection recovers.', retry: 'Try again',
  selected: 'Selected order', pickupLoading: 'Loading pickup status…', pickupUnavailable: 'Pickup status is unavailable.', pickupStale: 'Pickup status may be out of date.', pickupMalformed: 'AYO could not safely read pickup status.', pickupAuthorityLost: 'Pickup access is no longer available.',
  courier_assigned: 'Courier assigned', travelling_to_merchant: 'Courier travelling to merchant', arrived_at_merchant: 'Courier arrived at merchant', waiting_for_pickup: 'Waiting for pickup', pickup_attempt_ended_before_custody: 'Pickup attempt ended',
  waiting_for_merchant_confirmation: 'Awaiting merchant confirmation', accepted: 'Accepted', rejected: 'Rejected', preparing: 'Preparing', ready_for_pickup: 'Ready for pickup', orderLabel: 'Order', createdLabel: 'Created',
  acknowledgeArrival: 'Acknowledge arrival', acknowledgingArrival: 'Acknowledging arrival…', arrivalAcknowledged: 'Arrival acknowledged', checkArrivalStatus: 'Check status', checkingArrivalStatus: 'Checking status…', arrivalOutcomeUnknown: 'We could not confirm the result yet.', arrivalRetryAvailable: 'The same acknowledgement can be tried again.', tryArrivalAgain: 'Try again', arrivalNotAcknowledged: 'Arrival was not acknowledged.',
} as const;
type Copy = { readonly [K in keyof typeof english]: string };
const amharic: Copy = {
  heading: 'የሥራ ትዕዛዞች', help: 'የመልእክተኛውን የማንሳት ሁኔታ ለማየት ትዕዛዝ ይምረጡ።', refresh: 'ትዕዛዞችን አድስ', refreshing: 'ትዕዛዞች እየታደሱ ነው…',
  loading: 'ትዕዛዞችዎ እየተጫኑ ነው…', empty: 'አሁን የሚታይ ትዕዛዝ የለም።', unavailable: 'ትዕዛዞች ለጊዜው አይገኙም።', authorityLost: 'ይህ የንግድ ክፍል ከእንግዲህ አይገኝም።', malformed: 'AYO እነዚህን ትዕዛዞች በደህና ማንበብ አልቻለም።', stale: 'ግንኙነቱ እስኪመለስ ድረስ የቀድሞ መረጃ እየታየ ነው።', retry: 'እንደገና ሞክር',
  selected: 'የተመረጠ ትዕዛዝ', pickupLoading: 'የማንሳት ሁኔታ እየተጫነ ነው…', pickupUnavailable: 'የማንሳት ሁኔታ አይገኝም።', pickupStale: 'የማንሳት ሁኔታው ያረጀ ሊሆን ይችላል።', pickupMalformed: 'AYO የማንሳት ሁኔታውን በደህና ማንበብ አልቻለም።', pickupAuthorityLost: 'የማንሳት መዳረሻ ከእንግዲህ የለም።',
  courier_assigned: 'መልእክተኛ ተመድቧል', travelling_to_merchant: 'መልእክተኛው ወደ ንግዱ እየመጣ ነው', arrived_at_merchant: 'መልእክተኛው ንግዱ ጋር ደርሷል', waiting_for_pickup: 'ለማንሳት በመጠበቅ ላይ', pickup_attempt_ended_before_custody: 'የማንሳት ሙከራው አብቅቷል',
  waiting_for_merchant_confirmation: 'የንግዱን ማረጋገጫ በመጠበቅ ላይ', accepted: 'ተቀባይነት አግኝቷል', rejected: 'ውድቅ ተደርጓል', preparing: 'በዝግጅት ላይ', ready_for_pickup: 'ለመነሳት ዝግጁ', orderLabel: 'ትዕዛዝ', createdLabel: 'የተፈጠረበት',
  acknowledgeArrival: 'መድረሱን አረጋግጥ', acknowledgingArrival: 'መድረሱ እየተረጋገጠ ነው…', arrivalAcknowledged: 'መድረሱ ተረጋግጧል', checkArrivalStatus: 'ሁኔታውን ይመልከቱ', checkingArrivalStatus: 'ሁኔታው እየታየ ነው…', arrivalOutcomeUnknown: 'ውጤቱን እስካሁን ማረጋገጥ አልቻልንም።', arrivalRetryAvailable: 'ይኸው ማረጋገጫ እንደገና ሊሞከር ይችላል።', tryArrivalAgain: 'እንደገና ሞክር', arrivalNotAcknowledged: 'መድረሱ አልተረጋገጠም።',
};

// NEEDS_NATIVE_AMHARIC_REVIEW: courier-pickup and arrival-acknowledgement operational wording before production release.
export const merchantOperationalOrderCopy: Readonly<Record<SupportedLocale, Copy>> = { en: english, am: amharic };
