const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const HASH = /^[a-f0-9]{64}$/;
const VERSION = /^[a-z0-9][a-z0-9_.-]{0,62}$/;
const CONSENT_ID = /^[a-z][a-z0-9_.-]{2,127}$/;
const CONTROL = /[\u0000-\u001f\u007f-\u009f]/;

export class BookingContractError extends Error { constructor() { super('malformed_booking_contract'); } }
type RecordValue = Record<string, unknown>;
function record(value: unknown, keys: readonly string[]): RecordValue {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype) throw new BookingContractError();
  const ownKeys=Reflect.ownKeys(value);
  if(ownKeys.some(key=>typeof key!=='string')||ownKeys.length!==keys.length||!keys.every(key=>ownKeys.includes(key))) throw new BookingContractError();
  const normalized:RecordValue={};
  for(const key of keys){const descriptor=Object.getOwnPropertyDescriptor(value,key);if(!descriptor||!descriptor.enumerable||!('value' in descriptor))throw new BookingContractError();normalized[key]=descriptor.value;}
  return normalized;
}
function array(value:unknown,min:number,max:number):readonly unknown[]{if(!Array.isArray(value)||value.length<min||value.length>max)throw new BookingContractError();const keys=Reflect.ownKeys(value);const expected=[...Array(value.length)].map((_,index)=>String(index));if(keys.some(key=>typeof key!=='string'||(key!=='length'&&!expected.includes(key)))||!expected.every(key=>keys.includes(key)))throw new BookingContractError();const result:unknown[]=[];for(const key of expected){const descriptor=Object.getOwnPropertyDescriptor(value,key);if(!descriptor||!descriptor.enumerable||!('value' in descriptor))throw new BookingContractError();result.push(descriptor.value);}return result;}
function text(value: unknown, min = 1, max = 160): string { if (typeof value !== 'string' || value.length < min || value.length > max || CONTROL.test(value)) throw new BookingContractError(); return value; }
function nullableText(value: unknown, max: number): string | null { return value === null ? null : text(value, 0, max); }
function integer(value: unknown, min: number, max: number): number { if (!Number.isSafeInteger(value) || (value as number) < min || (value as number) > max) throw new BookingContractError(); return value as number; }
function finite(value: unknown, min: number, max: number): number { if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) throw new BookingContractError(); return value; }
function uuid(value: unknown): string { const result=text(value,36,36); if(!UUID.test(result)) throw new BookingContractError(); return result.toLowerCase(); }
function hash(value: unknown): string { const result=text(value,64,64); if(!HASH.test(result)) throw new BookingContractError(); return result; }
function timestamp(value: unknown): string { const result=text(value,20,35); const match=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/.exec(result); if(!match) throw new BookingContractError(); const [year,month,day,hour,minute,second]=match.slice(1,7).map(Number); const calendar=new Date(Date.UTC(year,month-1,day)); if(calendar.getUTCFullYear()!==year||calendar.getUTCMonth()!==month-1||calendar.getUTCDate()!==day||hour>23||minute>59||second>59) throw new BookingContractError(); if(match[7]!=='Z'){const [offsetHour,offsetMinute]=match[7].slice(1).split(':').map(Number);if(offsetHour>14||offsetMinute>59||(offsetHour===14&&offsetMinute!==0))throw new BookingContractError();} if(!Number.isFinite(Date.parse(result))) throw new BookingContractError(); return result; }
function literal<T extends string>(value: unknown, values: readonly T[]): T { if(typeof value!=='string'||!values.includes(value as T)) throw new BookingContractError(); return value as T; }

const SOURCES = ['rider_selected','device_observation','structured_address','landmark'] as const;
const SAFETY = ['unverified','recommended','restricted'] as const;
const PLACE_KINDS = ['address','landmark','verified_pickup_zone','verified_dropoff_zone','airport','hospital','shopping_centre','university','hotel','office','transport_hub'] as const;
const TRAFFIC = ['available','partial','unavailable','not_requested'] as const;
const TOLLS = ['available','none_evidenced','unsupported','unknown'] as const;
const LOCATION_KEYS = ['coordinate','source','observed_at','accuracy_metres','structured_address','landmark_reference','note','map_confidence_bps'] as const;
const PICKUP_KEYS = [...LOCATION_KEYS,'entrance_reference','exact_stop_reference','airport_terminal_reference','airport_zone_reference','reference_photo_metadata_reference','safety_status','policy_version'] as const;

export type BookingCoordinate = Readonly<{ latitude:number; longitude:number }>;
export type BookingLocationInput = Readonly<{ coordinate:BookingCoordinate; source:typeof SOURCES[number]; observed_at:string; accuracy_metres:number|null; structured_address:string|null; landmark_reference:string|null; note:string|null; map_confidence_bps:number }>;
export type BookingPickupInput = Readonly<BookingLocationInput & { entrance_reference:string|null; exact_stop_reference:string|null; airport_terminal_reference:string|null; airport_zone_reference:string|null; reference_photo_metadata_reference:string|null; safety_status:typeof SAFETY[number]; policy_version:string }>;
export type BookingPreviewInput = Readonly<{ pickup:BookingPickupInput; destination:BookingLocationInput; service_type:'immediate_standard' }>;
export type BookingPreviewWireRequest = Readonly<{ client_preview_id:string; booking_session:string; pickup:Readonly<BookingPickupInput & {pickup_id:string}>; destination:Readonly<BookingLocationInput & {destination_id:string}>; service_type:'immediate_standard' }>;
export type GeneratedBookingIdentifiers=Readonly<{intentId:string;clientPreviewId:string;bookingSession:string;pickupId:string;destinationId:string}>;

export function parseGeneratedBookingIdentifiers(value:Readonly<{intentId:unknown;clientPreviewId:unknown;bookingSession:unknown;pickupId:unknown;destinationId:unknown}>):GeneratedBookingIdentifiers{const result=Object.freeze({intentId:uuid(value.intentId),clientPreviewId:uuid(value.clientPreviewId),bookingSession:(()=>{const item=text(value.bookingSession,32,128);if(!/^[A-Za-z0-9_-]+$/.test(item))throw new BookingContractError();return item;})(),pickupId:uuid(value.pickupId),destinationId:uuid(value.destinationId)});if(new Set(Object.values(result)).size!==5)throw new BookingContractError();return result;}

function coordinate(value: unknown): BookingCoordinate { const v=record(value,['latitude','longitude']); return Object.freeze({latitude:finite(v.latitude,-90,90),longitude:finite(v.longitude,-180,180)}); }
function location(value: unknown, keys: readonly string[]): BookingLocationInput {
  const v=record(value,keys); const accuracy=v.accuracy_metres===null?null:finite(v.accuracy_metres,Number.MIN_VALUE,10_000);
  return Object.freeze({coordinate:coordinate(v.coordinate),source:literal(v.source,SOURCES),observed_at:timestamp(v.observed_at),accuracy_metres:accuracy,structured_address:nullableText(v.structured_address,512),landmark_reference:nullableText(v.landmark_reference,128),note:nullableText(v.note,280),map_confidence_bps:integer(v.map_confidence_bps,0,10_000)});
}
export function parseBookingPreviewInput(value: unknown): BookingPreviewInput {
  const top=record(value,['pickup','destination','service_type']); const p=record(top.pickup,PICKUP_KEYS); const base=location(top.pickup,PICKUP_KEYS);
  const policy=text(p.policy_version,1,63); if(!VERSION.test(policy)) throw new BookingContractError();
  const pickup=Object.freeze({...base,entrance_reference:nullableText(p.entrance_reference,128),exact_stop_reference:nullableText(p.exact_stop_reference,128),airport_terminal_reference:nullableText(p.airport_terminal_reference,128),airport_zone_reference:nullableText(p.airport_zone_reference,128),reference_photo_metadata_reference:nullableText(p.reference_photo_metadata_reference,128),safety_status:literal(p.safety_status,SAFETY),policy_version:policy});
  return Object.freeze({pickup,destination:location(top.destination,LOCATION_KEYS),service_type:literal(top.service_type,['immediate_standard'] as const)});
}
export function createBookingPreviewWireRequest(input: BookingPreviewInput, ids: Pick<GeneratedBookingIdentifiers,'clientPreviewId'|'bookingSession'|'pickupId'|'destinationId'>): BookingPreviewWireRequest {
  return Object.freeze({client_preview_id:ids.clientPreviewId,booking_session:ids.bookingSession,pickup:Object.freeze({...input.pickup,coordinate:Object.freeze({...input.pickup.coordinate}),pickup_id:ids.pickupId}),destination:Object.freeze({...input.destination,coordinate:Object.freeze({...input.destination.coordinate}),destination_id:ids.destinationId}),service_type:'immediate_standard'});
}
export function sameBookingPreviewInput(left: BookingPreviewInput, right: BookingPreviewInput): boolean {
  const locationEqual=(a:BookingLocationInput,b:BookingLocationInput)=>a.coordinate.latitude===b.coordinate.latitude&&a.coordinate.longitude===b.coordinate.longitude&&a.source===b.source&&a.observed_at===b.observed_at&&a.accuracy_metres===b.accuracy_metres&&a.structured_address===b.structured_address&&a.landmark_reference===b.landmark_reference&&a.note===b.note&&a.map_confidence_bps===b.map_confidence_bps;
  return left.service_type===right.service_type&&locationEqual(left.destination,right.destination)&&locationEqual(left.pickup,right.pickup)&&left.pickup.entrance_reference===right.pickup.entrance_reference&&left.pickup.exact_stop_reference===right.pickup.exact_stop_reference&&left.pickup.airport_terminal_reference===right.pickup.airport_terminal_reference&&left.pickup.airport_zone_reference===right.pickup.airport_zone_reference&&left.pickup.reference_photo_metadata_reference===right.pickup.reference_photo_metadata_reference&&left.pickup.safety_status===right.pickup.safety_status&&left.pickup.policy_version===right.pickup.policy_version;
}

export type BookingPlace = Readonly<{ placeReference:string; displayName:string; secondaryText?:string; kind:typeof PLACE_KINDS[number]; latitude:number; longitude:number; verifiedForPickup:boolean; verifiedForDropoff:boolean; attribution:string }>;
export function parseBookingPlaces(value: unknown): readonly BookingPlace[] { return Object.freeze(array(value,0,10).map(item=>{const v=record(item,['place_reference','display_name','secondary_text','kind','latitude','longitude','verified_for_pickup','verified_for_dropoff','attribution']); if(typeof v.verified_for_pickup!=='boolean'||typeof v.verified_for_dropoff!=='boolean') throw new BookingContractError(); return Object.freeze({placeReference:text(v.place_reference,8,128),displayName:text(v.display_name,1,160),...(v.secondary_text===null?{}:{secondaryText:text(v.secondary_text,0,160)}),kind:literal(v.kind,PLACE_KINDS),latitude:finite(v.latitude,-90,90),longitude:finite(v.longitude,-180,180),verifiedForPickup:v.verified_for_pickup,verifiedForDropoff:v.verified_for_dropoff,attribution:text(v.attribution,1,160)}); })); }

export type BookingConsent = Readonly<{ requiredVersion:string; documentId:string; contentHash:string; acknowledgmentRequired:true }>;
export type BookingPreview = Readonly<{ evidenceId:string; evidenceHash:string; quoteId:string; currency:'ETB'; estimatedFareMinor:number; pricingVersion:string; expiresAt:string; consent:BookingConsent }>;
export function parseBookingPreview(value: unknown, now=Date.now()): BookingPreview {
  const v=record(value,['evidence_id','evidence_hash','pickup','destination','geometry','distance_metres','duration_seconds','traffic_state','toll_state','toll_amount_minor','toll_message','quote_id','currency','estimated_fare_minor','pricing_version','fare_explanation','surge_applied','expires_at','attribution','consent']);
  text(v.pickup,1,512); text(v.destination,1,512); integer(v.distance_metres,1,2_000_000); integer(v.duration_seconds,1,172_800); literal(v.traffic_state,TRAFFIC); const toll=literal(v.toll_state,TOLLS);
  for(const point of array(v.geometry,2,512)){const values=array(point,2,2);finite(values[0],-90,90);finite(values[1],-180,180);}
  const tollAmount=v.toll_amount_minor===null?null:integer(v.toll_amount_minor,0,10_000_000_000); const tollMessage=v.toll_message===null?null:text(v.toll_message,1,160);
  if((toll==='available')!==(tollAmount!==null)||((toll==='unknown'||toll==='unsupported')!==(tollMessage!==null))||(toll==='none_evidenced'&&tollMessage!==null)) throw new BookingContractError();
  for(const item of array(v.fare_explanation,1,16)) text(item,1,160); if(typeof v.surge_applied!=='boolean') throw new BookingContractError(); text(v.attribution,1,160);
  if(v.currency!=='ETB') throw new BookingContractError(); const pricingVersion=text(v.pricing_version,1,63); if(!VERSION.test(pricingVersion)) throw new BookingContractError();
  const expiresAt=timestamp(v.expires_at); if(Date.parse(expiresAt)<=now) throw new BookingContractError(); const c=record(v.consent,['required_version','document_id','content_hash','acknowledgment_required']); if(c.acknowledgment_required!==true) throw new BookingContractError();
  const requiredVersion=text(c.required_version,3,63), documentId=text(c.document_id,3,128); if(!CONSENT_ID.test(requiredVersion)||!CONSENT_ID.test(documentId)) throw new BookingContractError();
  return Object.freeze({evidenceId:uuid(v.evidence_id),evidenceHash:hash(v.evidence_hash),quoteId:uuid(v.quote_id),currency:'ETB',estimatedFareMinor:integer(v.estimated_fare_minor,0,10_000_000_000),pricingVersion,expiresAt,consent:Object.freeze({requiredVersion,documentId,contentHash:hash(c.content_hash),acknowledgmentRequired:true})});
}
