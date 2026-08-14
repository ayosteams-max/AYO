import { parseBookingPlaces, type BookingPlace, type BookingPreviewWireRequest } from '../domain/booking-contracts.ts';
import { boundedFetch, parsePublicError, PublicApiError, validateApiBaseUrl } from './api-foundation.ts';

export interface BookingSessionAccess { accessToken():Promise<string>; forceRefresh(expectedToken?:string):Promise<Readonly<{accessToken:string}>|undefined>; }
export class BookingApi {
  private readonly baseUrl:string; private readonly sessions:BookingSessionAccess; private readonly request:typeof fetch;
  constructor(baseUrl:string,sessions:BookingSessionAccess,request:typeof fetch=fetch){this.baseUrl=validateApiBaseUrl(baseUrl);this.sessions=sessions;this.request=request;}
  async search(query:string,locale:'en'|'am',limit:number,signal?:AbortSignal):Promise<readonly BookingPlace[]>{if(signal?.aborted)throw new PublicApiError('request_cancelled');if(typeof query!=='string'||query.length<2||query.length>120||CONTROL.test(query)||(locale!=='en'&&locale!=='am')||!Number.isInteger(limit)||limit<1||limit>10) throw new Error('invalid_booking_search');return parseBookingPlaces(await this.send(`/mobile/booking/places/search?query=${encodeURIComponent(query)}&locale=${locale}&limit=${limit}`,{method:'GET',signal}));}
  async preview(input:BookingPreviewWireRequest,signal?:AbortSignal):Promise<unknown>{if(signal?.aborted)throw new PublicApiError('request_cancelled');return this.send('/mobile/booking/route-previews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input),signal});}
  private async send(path:string,init:RequestInit):Promise<unknown>{const token=await this.sessions.accessToken();let response=await this.fetch(path,token,init);if(response.status===401){const refreshed=await this.sessions.forceRefresh(token);if(!refreshed) throw new PublicApiError('session_expired',401);response=await this.fetch(path,refreshed.accessToken,init);}if(!response.ok) throw await parsePublicError(response);try{return await response.json();}catch{throw new PublicApiError('malformed_response',response.status);}}
  private fetch(path:string,token:string,init:RequestInit){return boundedFetch(this.request,`${this.baseUrl}${path}`,{...init,headers:{Accept:'application/json',Authorization:`Bearer ${token}`,...init.headers}});}
}
const CONTROL=/[\u0000-\u001f\u007f-\u009f]/;
