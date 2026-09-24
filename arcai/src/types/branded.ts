export type Brand<T, B extends string> = T & { readonly __brand: B };

export type Address = Brand<`0x${string}`, "Address">;
export type Hex = Brand<`0x${string}`, "Hex">;
export type TxHash = Brand<`0x${string}`, "TxHash">;
export type BlockHash = Brand<`0x${string}`, "BlockHash">;

export type ChainId = Brand<number, "ChainId">;
export type BlockNumber = Brand<bigint, "BlockNumber">;
export type UnixMs = Brand<number, "UnixMs">;
export type Iso8601 = Brand<string, "Iso8601">;

export type BasisPoints = Brand<number, "BasisPoints">;
export type Score0to100 = Brand<number, "Score0to100">;

export type UserId = Brand<string, "UserId">;
export type RequestId = Brand<string, "RequestId">;
export type SignalId = Brand<string, "SignalId">;
export type TradeIntentId = Brand<string, "TradeIntentId">;
