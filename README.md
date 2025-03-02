# Yasal Uyarı
Bu projenin amacı, geçmiş maç oranlarını analiz ederek oranlar ile ilgili istatistiksel bilgiler sunmaktır. OranAnaliz, yalnızca oranları analiz eder ve herhangi bir bahis oynama, yönlendirme veya teşvik etme amacı taşımaz.

# Ayarlar
⚙️ Kullanıcı Tarafından Değiştirilebilecek Ayarlar

OranAnaliz projesinde kullanıcıların ihtiyaçlarına göre değiştirebileceği bazı ayarlar bulunmaktadır. Aşağıda, değiştirilebilecek kısımlar ve bunların ne işe yaradıkları açıklanmıştır.


1️⃣ Analiz Edilecek Geçmiş Maç Aralığı

📍 Bulunduğu Yer: get_date_range_choice() fonksiyonu
📍 Kod İçindeki Kısım:

ranges = {
    "1": 1, "2": 3, "3": 5, "4": 7,
    "5": 30, "6": 90, "7": 180, "8": 365
}

📌 Açıklama:
Kullanıcı analiz yaparken, geçmiş kaç gün içindeki maçları kontrol etmek istediğini seçer. Varsayılan seçenekler 1 gün, 3 gün, 1 hafta, 1 ay vb. olarak belirlenmiştir.

2️⃣ Benzer Maçları Belirleme Eşiği

📍 Bulunduğu Yer: find_similar_matches() fonksiyonu
📍 Kod İçindeki Kısım:

threshold = 0.05

📌 Açıklama:
Oran karşılaştırmalarında 0.05 varsayılan eşik değeridir. Bu, bugünkü oranlar ile geçmiş oranlar arasındaki farkın %5’ten az olması durumunda maçı benzer olarak kabul eder.

3️⃣ Kaydedilen Dosya Konumu

📍 Bulunduğu Yer: get_base_directory() fonksiyonu
📍 Kod İçindeki Kısım:

if os_type == "windows":
    return "C:\\Oran Analiz"
elif "linux" in os_type:
    return "/storage/emulated/0/Oran Analiz"

📌 Açıklama:
Bu ayar, analiz sonuçlarının hangi klasöre kaydedileceğini belirler. Windows ve Linux için ayrı yollar belirtilmiştir.

4️⃣ Güncellenmesi Gereken Günlük Veri Aralığı

📍 Bulunduğu Yer: auto_update_data() fonksiyonu
📍 Kod İçindeki Kısım:

start_date = end_date - timedelta(days=3)

📌 Açıklama:
Program açıldığında otomatik olarak son 3 günün maçlarını günceller.

