import { describe, expect, it } from 'vitest';

import { bungkus, susunEscposFoto, susunEscposTeks } from './escpos';

// Acuan dibangkitkan dari backend/services/thermal_printer.py (susun_escpos_teks / susun_escpos)
// dengan masukan yang sama, jadi cetak lewat BLE dan lewat backend menghasilkan byte identik.
const hex = (u: Uint8Array) => Array.from(u, (b) => b.toString(16).padStart(2, '0')).join('');

const BARIS = [
  {
    "teks": "Tiket Rencana Perjalanan",
    "tebal": true,
    "besar": true,
    "tengah": true
  },
  {
    "garis": true
  },
  {
    "teks": "Dari",
    "kanan": "Harmoni"
  },
  {
    "teks": "Tiba (perkiraan)",
    "kanan": "16.55"
  },
  {
    "teks": "Halte Tujuan Yang Namanya Sangat Panjang Sekali Sampai Harus Dibungkus Beberapa Baris Karena Melebihi Lebar",
    "kanan": "Pulo Gadung Terminal Utama"
  },
  {
    "teks": "Koridor 1 - Blok M",
    "tebal": true
  },
  {
    "teks": "Naik di Harmoni lalu turun di Kota selama kira-kira dua puluh lima menit perjalanan bus Transjakarta hari ini",
    "tengah": true
  },
  {
    "teks": "Café ganjil",
    "tengah": true
  },
  {
    "teks": "Verylongwordwithoutanyspacesthatexceedsfortyeightcharactersforsureyesindeed"
  },
  {
    "teks": ""
  }
];

const TEKS_ACUAN = '1b401b45011d210120202020202020202020202054696b65742052656e63616e61205065726a616c616e616e1d21001b45000a2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d0a44617269202020202020202020202020202020202020202020202020202020202020202020202020204861726d6f6e690a5469626120287065726b697261616e2920202020202020202020202020202020202020202020202020202031362e35350a48616c74652054756a75616e2059616e67204e616d616e79612053616e6761742050616e6a616e672053656b616c690a53616d70616920486172757320446962756e676b7573204265626572617061204261726973204b6172656e610a4d656c6562696869204c656261720a2020202020202020202020202020202020202020202050756c6f20476164756e67205465726d696e616c205574616d610a1b45014b6f7269646f722031202d20426c6f6b204d1b45000a4e61696b206469204861726d6f6e69206c616c7520747572756e206469204b6f74612073656c616d61206b6972612d0a202020206b697261206475612070756c7568206c696d61206d656e6974207065726a616c616e616e206275730a202020202020202020202020205472616e736a616b61727461206861726920696e690a2020202020202020202020202020202020204361663f2067616e6a696c0a566572796c6f6e67776f7264776974686f7574616e797370616365737468617465786365656473666f727479656967680a7463686172616374657273666f7273757265796573696e646565640a0a0a0a0a0a';

const FOTO_ACUAN = '1b401d76300002004000030a11181f262d343b424950575e656c737a81888f969da4abb2b9c0c7ced5dce3eaf1f8ff060d141b222930373e454c535a61686f767d848b9299a0a7aeb5bcc3cad1d8dfe6edf4fb020910171e252c333a41484f565d646b727980878e959ca3aab1b8bfc6cdd4dbe2e9f0f7fe050c131a21282f363d444b525960676e757c1d76300002000600838a91989fa6adb4bbc2c9d00a466f746f2050686f746f626f780a4361663f0a0a0a0a0a';

describe('susunEscposTeks', () => {
  it('identik dengan keluaran backend', () => {
    expect(hex(susunEscposTeks(BARIS))).toBe(TEKS_ACUAN);
  });
});

describe('susunEscposFoto', () => {
  it('identik dengan keluaran backend', () => {
    const bits = Uint8Array.from(atob('AwoRGB8mLTQ7QklQV15lbHN6gYiPlp2kq7K5wMfO1dzj6vH4/wYNFBsiKTA3PkVMU1phaG92fYSLkpmgp661vMPK0djf5u30+wIJEBceJSwzOkFIT1ZdZGtyeYCHjpWco6qxuL/GzdTb4unw9/4FDBMaISgvNj1ES1JZYGdudXyDipGYn6attLvCydA='), (c) => c.charCodeAt(0));
    expect(hex(susunEscposFoto(16, 70, bits, ["Foto Photobox", "Café"]))).toBe(FOTO_ACUAN);
  });

  it('menolak bitmap yang ukurannya tidak cocok', () => {
    expect(() => susunEscposFoto(16, 4, new Uint8Array(3), [])).toThrow();
  });
});

describe('bungkus', () => {
  it('string kosong menjadi tanpa baris', () => {
    expect(bungkus('', 10)).toEqual([]);
  });
});
