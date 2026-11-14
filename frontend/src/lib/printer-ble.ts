// Kirim byte ESC/POS ke printer thermal lewat Web Bluetooth (BLE GATT), langsung dari browser.
// Hanya Chrome/Edge (Android + desktop) di HTTPS atau localhost; Safari/iOS tidak mendukung.

// Subset Web Bluetooth yang dipakai (lib.dom belum memuatnya).
type Karakteristik = {
  uuid: string;
  properties: { write: boolean; writeWithoutResponse: boolean };
  writeValueWithResponse(v: BufferSource): Promise<void>;
  writeValueWithoutResponse(v: BufferSource): Promise<void>;
};
type Layanan = { getCharacteristics(): Promise<Karakteristik[]> };
type ServerGatt = { connected: boolean; connect(): Promise<ServerGatt>; disconnect(): void; getPrimaryServices(): Promise<Layanan[]> };
type PerangkatBle = { name?: string; gatt?: ServerGatt };
type BluetoothApi = {
  requestDevice(opsi: { filters: { namePrefix: string }[]; optionalServices: string[] }): Promise<PerangkatBle>;
};

export class GalatBle extends Error {
  constructor(
    readonly jenis: 'tidak-didukung' | 'dibatalkan' | 'tidak-ada-tulis' | 'gagal',
    pesan: string,
  ) {
    super(pesan);
  }
}

// Nama iklan RPP02N diawali "RPP". Layanan tulis printer thermal murah tidak baku, jadi daftar
// UUID yang lazim dipakai dicoba semua; karakteristik pertama yang bisa ditulis dipakai.
const AWALAN_NAMA = ['RPP'];
const LAYANAN_LAZIM = [
  '000018f0-0000-1000-8000-00805f9b34fb',
  '0000ff00-0000-1000-8000-00805f9b34fb',
  '0000ffe0-0000-1000-8000-00805f9b34fb',
  '0000fee7-0000-1000-8000-00805f9b34fb',
  '0000ae30-0000-1000-8000-00805f9b34fb',
  '49535343-fe7d-4ae5-8fa9-9fafd205e455',
  'e7810a71-73ae-499d-8c15-faa9aef0c3f2',
];

// Potongan kecil + jeda: buffer printer kecil dan MTU BLE default (20 byte) cepat penuh.
const UKURAN_POTONG = 100;
const JEDA_POTONG_MS = 20;

let perangkat: PerangkatBle | null = null;
let tulis: Karakteristik | null = null;

const bluetooth = (): BluetoothApi | undefined => (navigator as Navigator & { bluetooth?: BluetoothApi }).bluetooth;

export const bleDidukung = (): boolean => typeof navigator !== 'undefined' && !!bluetooth();

async function cariKarakteristikTulis(server: ServerGatt): Promise<Karakteristik> {
  for (const layanan of await server.getPrimaryServices()) {
    for (const k of await layanan.getCharacteristics()) {
      if (k.properties.writeWithoutResponse || k.properties.write) return k;
    }
  }
  throw new GalatBle('tidak-ada-tulis', 'Printer tidak punya karakteristik tulis BLE yang dikenali.');
}

// Pemilihan perangkat wajib dipanggil dari klik pengguna. Setelah itu sambungan dipakai ulang;
// bila putus, disambung lagi tanpa dialog.
async function pastikanTersambung(): Promise<Karakteristik> {
  if (perangkat?.gatt?.connected && tulis) return tulis;
  try {
    if (!perangkat) {
      perangkat = await bluetooth()!.requestDevice({
        filters: AWALAN_NAMA.map((namePrefix) => ({ namePrefix })),
        optionalServices: LAYANAN_LAZIM,
      });
    }
    tulis = await cariKarakteristikTulis(await perangkat.gatt!.connect());
    return tulis;
  } catch (err) {
    perangkat = null;
    tulis = null;
    if (err instanceof GalatBle) throw err;
    if (err instanceof DOMException && err.name === 'NotFoundError') throw new GalatBle('dibatalkan', 'Pemilihan printer dibatalkan.');
    throw new GalatBle('gagal', err instanceof Error ? err.message : 'Gagal menyambung ke printer.');
  }
}

export async function kirimBle(data: Uint8Array): Promise<void> {
  if (!bleDidukung()) throw new GalatBle('tidak-didukung', 'Browser ini tidak mendukung Web Bluetooth.');
  const k = await pastikanTersambung();
  try {
    for (let i = 0; i < data.length; i += UKURAN_POTONG) {
      const potong = data.slice(i, i + UKURAN_POTONG);
      if (k.properties.writeWithoutResponse) await k.writeValueWithoutResponse(potong);
      else await k.writeValueWithResponse(potong);
      await new Promise((r) => setTimeout(r, JEDA_POTONG_MS));
    }
  } catch (err) {
    perangkat?.gatt?.disconnect();
    tulis = null;
    throw new GalatBle('gagal', err instanceof Error ? err.message : 'Gagal mengirim data ke printer.');
  }
}
