import type { BookingIntentRecord } from '../domain/booking-intent.ts';

function immutable(intent:BookingIntentRecord):BookingIntentRecord{return Object.freeze({...intent,input:intent.input?Object.freeze({...intent.input,pickup:Object.freeze({...intent.input.pickup,coordinate:Object.freeze({...intent.input.pickup.coordinate})}),destination:Object.freeze({...intent.input.destination,coordinate:Object.freeze({...intent.input.destination.coordinate})})}):undefined,request:intent.request?Object.freeze({...intent.request,pickup:Object.freeze({...intent.request.pickup,coordinate:Object.freeze({...intent.request.pickup.coordinate})}),destination:Object.freeze({...intent.request.destination,coordinate:Object.freeze({...intent.request.destination.coordinate})})}):undefined,preview:intent.preview?Object.freeze({...intent.preview,consent:Object.freeze({...intent.preview.consent})}):undefined});}
export class InMemoryBookingIntentStore {
  private current?:BookingIntentRecord;
  read():BookingIntentRecord|undefined{return this.current?immutable(this.current):undefined;}
  replace(intent:BookingIntentRecord):void{this.current=immutable(intent);}
  clear():void{this.current=undefined;}
}
