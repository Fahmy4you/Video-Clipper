// Compare dates in the user's local calendar; both range endpoints are inclusive.
export function localDay(value:string){const d=new Date(value);return Number.isNaN(d.getTime())?'':`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
export function inDateRange(value:string,from:string,to:string){if(!from&&!to)return true;const day=localDay(value);return !!day&&(!from||day>=from)&&(!to||day<=to)}
export function compareNames(a:string,b:string){return a.localeCompare(b,'id',{sensitivity:'base',numeric:true})}
export function compareDates(a:string,b:string,ascending=false){const left=Date.parse(a),right=Date.parse(b);if(!Number.isFinite(left))return Number.isFinite(right)?1:0;if(!Number.isFinite(right))return -1;return (left-right)*(ascending?1:-1)}
