# Panduan kebijakan

*Untuk pemangku kepentingan pemerintah, organisasi masyarakat sipil (OMS/CSO),
dan mitra pembangunan: apa yang dijawab Garuda, cara membaca hasilnya, dan hal
yang perlu diwaspadai — tanpa perlu latar belakang pemodelan.*

*Terjemahan dari [`guide_policy.md`](guide_policy.md) (bahasa Inggris).
Terjemahan ini disusun dengan cermat namun tetap merupakan draf — koreksi dari
penutur asli dan mitra sangat kami harapkan.*

Anda tidak perlu menjalankan model untuk memakai panduan ini; panduan ini
menjelaskan cara menafsirkan laporan Garuda dan di mana posisi alat ini. Untuk
meminta sebuah run, seorang analis dapat mengikuti
[`guide_analyst.md`](guide_analyst.md) lalu menyerahkan laporan otomatisnya —
laporan itu dapat dibuat dalam Bahasa Indonesia:
`python tools/report.py <folder_hasil> --lang id`.

## Apa itu Garuda — dan apa yang bukan

Garuda adalah **lapisan koordinasi beresolusi situs** untuk sistem
ketenagalistrikan Indonesia. Ia merepresentasikan negara sebagai **pulau → zona
jaringan → situs desa / kawasan industri**, dan dalam satu model
mengoptimalkan secara bersama keputusan *terdistribusi* (PLTS desa + baterai +
diesel, atau pembangkit captive sebuah kawasan industri) **dengan** ekspansi
kapasitas jaringan zonal beserta operasinya jam demi jam.

Garuda sengaja **bukan** alat perencanaan sistem nasional yang lain. Ia
melengkapi lapisan-lapisan yang sudah terlayani dengan baik:

- **Model sistem / regional** (RUPTL PLN, RUKN, Scenario Builder milik
  TransitionZero) menentukan lintasan skala GW di tingkat transmisi. Garuda
  bekerja satu lapis lebih dalam, sampai ke situs, dan **mengekspor ke PyPSA**
  sehingga keduanya bisa saling diperiksa alih-alih saling menduplikasi.
- **Alat elektrifikasi** (GEP Bank Dunia / OnSSET) memilih jaringan vs
  mini-grid vs berdiri sendiri *per komunitas*. Garuda menambahkan apa yang
  tidak mereka lakukan — ko-optimisasi pilihan per situs itu terhadap
  pembangkitan dan operasi jaringan.

Klaim yang bisa dipertahankan memang sempit: Garuda menjawab *apa yang dibangun
di mana, bagaimana armada pembangkit beroperasi, dan nilai koordinasi antara
solusi terdistribusi dan jaringan* — pada resolusi yang dirata-ratakan hilang
oleh model nasional.

## Pertanyaan yang dijawabnya

- Bauran berbiaya terendah per situs: PLTS+baterai+diesel berdiri sendiri,
  perluasan jaringan, atau keduanya — beserta **nilai koordinasi** (penguatan
  jaringan dan diesel yang terhindarkan bila keduanya direncanakan *bersama*,
  bukan terpisah).
- Kapasitas, pembangkitan, biaya, emisi per zona, dan **keandalan** (di mana dan
  seberapa sering pasokan tidak mencukupi).
- Bagaimana lintasan transisi berubah di bawah kebijakan **clean** (batas emisi
  CO₂ dan batas minimum pangsa energi terbarukan) dibandingkan kasus referensi.

## Membaca laporan — metrik utama

Laporan otomatis ([`experience_layer.md`](experience_layer.md)) dibuka dengan:

| Metrik | Arti sederhana |
|---|---|
| **Total biaya sistem (juta US$/tahun)** | biaya tahunan sistem yang dimodelkan — angka untuk dibandingkan *antar skenario*, bukan dibaca mutlak |
| **Emisi CO₂ (ribu ton/tahun)** | emisi tahunan sektor ketenagalistrikan dalam cakupan model |
| **Pangsa energi terbarukan jaringan (%)** | porsi pembangkitan jaringan dari unit yang ditandai terbarukan (baca dengan hati-hati — lihat peringatan) |
| **Permintaan tahunan / Energi terlayani (GWh)** | listrik yang diminta vs yang benar-benar terpenuhi |
| **Energi tak terlayani (GWh) dan porsinya (%)** | defisit keandalan — permintaan yang **tidak** mampu dipenuhi armada pembangkit |

Perbandingan yang paling berguna adalah **dua skenario berdampingan** pada pulau
dan tahun yang sama — mis. `village` (semua berdiri sendiri) vs `gridvillage`
(terkoordinasi). *Selisihnya* — biaya, emisi, penguatan jaringan, energi tak
terlayani — itulah hasil yang relevan untuk kebijakan, bukan satu angka mutlak.
Alat [`coordination_value.md`](coordination_value.md) menghitung seluruh tabel
selisih itu dengan satu perintah.

## Bahasa skenario, dalam istilah sederhana

- **village / captive** — komunitas atau kawasan industri berdiri sendiri.
- **gridvillage / gridcaptive** — dikoordinasikan dengan jaringan (pertanyaan
  program 100 GW). Selisih terhadap kasus berdiri sendiri adalah manfaat
  koordinasinya.
- **reference vs clean** — `clean` memberlakukan batas emisi CO₂ ala JETP dan
  pangsa minimum energi terbarukan; `reference` tidak. Membandingkan keduanya
  memperlihatkan implikasi biaya dan pembangunan dari kebijakan tersebut.

## Hal yang perlu diwaspadai

Model adalah alat bantu keputusan, bukan ramalan. Sebelum mengutip sebuah angka:

1. **Provenans data masih kelas riset.** Input kredibel tetapi belum digantikan
   angka resmi PLN/ESDM/RUKN per zona dan situs. Perlakukan hasil sebagai
   *indikatif dan komparatif* sampai provenans ditingkatkan — ini butir teratas
   menuju penggunaan kelas keputusan. Asal setiap angka, dan sumber resmi mana
   yang akan menggantikannya, terdokumentasi berkas demi berkas di
   [`data_indonesia/DATA_PROVENANCE.md`](../data_indonesia/DATA_PROVENANCE.md).
2. **Sampel minggu representatif, bukan setahun penuh.** Model berjalan pada
   periode representatif yang diberi bobot setahun — kokoh untuk total tahunan,
   tidak untuk tanggal tertentu.
3. **Angka keandalan cenderung optimistis secara bawaan.** Dispatch cepat yang
   open-source melonggarkan sebagian batasan operasi pembangkit termal, sehingga
   energi tak terlayani cenderung menjadi taksiran bawah bila batasan itu
   mengikat.
4. **Periksa apa yang dihitung "pangsa energi terbarukan".** Angka ini mengikuti
   penanda terbarukan per unit di dalam data. Kesalahan penanda pernah terjadi
   dan telah dikoreksi — unit fosil tertanda terbarukan di maluku, lalu audit
   lanjutan di semua pulau yang mengembalikan 146 unit hidro/panas bumi
   (termasuk 768 MW potensi panas bumi) ke sisi terbarukan; pemeriksa skema kini
   memberi peringatan untuk kedua pola itu. Penanda ini sengaja menghitung
   energi terbarukan *yang dapat diatur* (hidro, panas bumi, bio, sampah), bukan
   hanya surya dan angin — jadi baca pangsa ini bersama bauran pembangkitan pada
   laporan yang sama.
5. **Biaya bersifat komparatif.** Gunakan selisih biaya antar skenario; angka
   mutlak juta US$/tahun bergantung pada cakupan pemodelan.

## Terbuka, dapat diaudit, dapat direproduksi

Garuda berjalan di atas solver open-source **HiGHS** — tanpa lisensi komersial —
sehingga kementerian, OMS, pengembang, maupun peneliti mana pun dapat
menjalankan dan mengauditnya di laptop, dan hasilnya dapat direproduksi secara
persis. Model yang dapat diaudit juga memunculkan kesalahan yang disembunyikan
alat proprietari (pekerjaan ini telah menemukan dan mengoreksi bug pemodelan
pada kode warisannya). Untuk rencana yang harus dipercaya banyak lembaga,
transparansi itu sendiri adalah fitur.
