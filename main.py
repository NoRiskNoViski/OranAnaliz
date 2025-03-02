import json
import requests
import pandas as pd
import os
import platform
import threading
from typing import Dict, List, Any, Tuple
from datetime import datetime, timedelta, timezone

def update_match_fields(existing_match: Dict, new_match: Dict) -> bool:
    """
    Mevcut maç verisini yeni veriyle günceller
    Returns: True if updated, False if no update needed
    """
    updated = False
    
    # SADECE detay API'sinden skorları kullan
    fts_A = new_match.get("fts_A")
    fts_B = new_match.get("fts_B")
    hts_A = new_match.get("hts_A") 
    hts_B = new_match.get("hts_B")
    
    # Güncellenecek alanlar
    fields_to_update = {
        "Status": new_match.get("Status"),
        "Period": new_match.get("Period"),
        "Tarih": new_match.get("Tarih"),
        "Saat": new_match.get("Saat")
    }
    
    # Skorlar varsa ekle
    if fts_A is not None and fts_B is not None:
        fields_to_update["Skor"] = f"{fts_A} - {fts_B}"
    
    if hts_A is not None and hts_B is not None:
        fields_to_update["İlk Yarı Skoru"] = f"{hts_A} - {hts_B}"

    # Market tiplerine göre oranları güncelle
    market_types = {
        "Maç Sonucu": ["1", "X", "2"],
        "İlk Yarı": ["1", "X", "2"],
        "Karşılıklı Gol": ["Var", "Yok"],
        "A/U 2.5": ["Üst", "Alt"],
        "IY 1.5": ["Üst", "Alt"],
        "Toplam Gol": ["0-1", "2-3", "4-5", "6+"],
        "EV 1.5": ["Üst", "Alt"],
        "DEP 1.5": ["Üst", "Alt"],
        "IY/MS": ["1/1", "1/X", "1/2", "X/1", "X/X", "X/2", "2/1", "2/X", "2/2"]
    }

    # Her market tipi için oranları kontrol et ve güncelle
    for market_type, outcomes in market_types.items():
        for outcome in outcomes:
            field_name = f"{market_type}_{outcome}"
            new_value = new_match.get(field_name)
            if new_value and new_value != existing_match.get(field_name):
                existing_match[field_name] = new_value
                updated = True

    # Temel alanları güncelle
    for field, new_value in fields_to_update.items():
        if new_value and new_value != existing_match.get(field):
            existing_match[field] = new_value
            updated = True

    return updated

def auto_update_data(historic_file: str) -> Dict:
    try:
        historic_data = load_historic_data(historic_file)
        if not historic_data.get("matches"):
            historic_data = {"matches": {}, "last_update": None}

        token = get_token()
        if not token:
            print("❌ Token alınamadı! Güncelleme yapılamıyor.")
            return historic_data

        current_time = datetime.now(timezone.utc)
        end_date = current_time
        start_date = end_date - timedelta(days=3)

        print(f"\n📊 {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')} arası maçlar güncelleniyor...")

        update_stats = {"new_matches": 0, "updated_matches": 0, "processed_days": 0, "errors": 0}
        
        def process_day(date_str):
            nonlocal update_stats
            try:
                daily_matches = get_matches_for_date(token, date_str)
                if not daily_matches:
                    print(f"❌ {date_str} için veri bulunamadı.")
                    return

                finished_matches = [match for match in daily_matches if match.get("Status") == 3]

                if finished_matches:
                    if date_str not in historic_data["matches"]:
                        historic_data["matches"][date_str] = finished_matches
                        update_stats["new_matches"] += len(finished_matches)
                    else:
                        existing_matches = historic_data["matches"][date_str]
                        existing_match_ids = {m.get("id"): m for m in existing_matches}

                        updated_count = 0
                        for new_match in finished_matches:
                            match_id = new_match.get("id")
                            if match_id in existing_match_ids:
                                if update_match_fields(existing_match_ids[match_id], new_match):
                                    updated_count += 1
                            else:
                                existing_matches.append(new_match)
                                update_stats["new_matches"] += 1

                        if updated_count > 0:
                            update_stats["updated_matches"] += updated_count

                    update_stats["processed_days"] += 1
                else:
                    print(f"❌ {date_str}: Bitmiş maç bulunamadı.")
            
            except Exception as e:
                update_stats["errors"] += 1
                print(f"❌ {date_str} verisi işlenirken hata: {str(e)}")

        # Asenkron işlem başlat
        threads = []
        check_date = start_date
        while check_date.date() <= end_date.date():
            date_str = check_date.strftime("%Y-%m-%d")
            thread = threading.Thread(target=process_day, args=(date_str,))
            threads.append(thread)
            thread.start()
            check_date += timedelta(days=1)

        # Tüm thread'lerin bitmesini bekle
        for thread in threads:
            thread.join()

        # Güncelleme tamamlandıktan sonra kaydet
        historic_data["last_update"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
        save_historic_data(historic_data, historic_file)

        print("\n📊 Güncelleme Özeti:")
        print(f"📅 İşlenen gün: {update_stats['processed_days']}")
        print(f"📈 Yeni maç: {update_stats['new_matches']}")
        print(f"🔄 Güncellenen maç: {update_stats['updated_matches']}")
        if update_stats["errors"] > 0:
            print(f"❌ Hatalı gün: {update_stats['errors']}")

        return historic_data

    except Exception as e:
        print(f"\n❌ Otomatik güncelleme hatası: {str(e)}")
        return historic_data

class MatchData:
    def __init__(self):
        self.market_types = {
            1: "Maç Sonucu",
            3: "İlk Yarı",
            6: "Karşılıklı Gol",
            8: "IY/MS",
            10: "A/U 2.5",
            11: "IY 1.5",
            13: "Toplam Gol",
            14: "EV 1.5",
            15: "DEP 1.5",
            16: "Maç Sonucu A/U"
        }

    def parse_match_data(self, match: Dict[str, Any]) -> Dict[str, Any]:
        match_data = {
            "id": match.get("id"),
            "uuid": match.get("uuid"),
            "Lig": match.get("title"),
            "Tarih": "",
            "Saat": match.get("time"),
            "Ev Sahibi": match.get("team_A"),
            "Deplasman": match.get("team_B"),
            "Status": match.get("Status", 1)
        }
        
        # SADECE detay API'sinden gelen skorları kullan
        fts_A = match.get("fts_A")
        fts_B = match.get("fts_B")
        
        # Tam skor
        if fts_A is not None and fts_B is not None:
            match_data["Skor"] = f"{fts_A} - {fts_B}"
        else:
            match_data["Skor"] = "- - -"
        
        # İlk yarı skoru
        hts_A = match.get("hts_A")
        hts_B = match.get("hts_B")
        if hts_A is not None and hts_B is not None:
            match_data["İlk Yarı Skoru"] = f"{hts_A} - {hts_B}"
        else:
            match_data["İlk Yarı Skoru"] = "- - -"

        # Bahis oranlarını ekle
        for market in match.get("markets", []):
            market_id = market.get("i")
            market_type = self.market_types.get(market_id)
            if not market_type:
                continue

            first_odds = market.get("o", [])
            if first_odds:
                for outcome in first_odds[0].get("l", []):
                    outcome_name = outcome.get("n")
                    outcome_value = outcome.get("v")
                    if outcome_value:
                        match_data[f"{market_type}_{outcome_name}"] = outcome_value

        return match_data

def get_token() -> str:
    """Mackolik API için token alır"""
    token_url = "https://www.mackolik.com/ajax/middleware/token"
    try:
        token_response = requests.get(token_url)
        token_response.raise_for_status()
        return token_response.json().get("data", {}).get("token")
    except requests.exceptions.RequestException as e:
        print(f"❌ Token hatası: {str(e)}")
        return None

def get_match_details(token: str, date: str) -> Dict:
    """Belirli bir tarihteki maçların ilk yarı skorlarını alır"""
    api_url = f"https://api.mackolikfeeds.com/api/matches/?language=tr&country=tr&add_playing=1&extended_period=1&date={date}&tz=3.0&application=com.kokteyl.mackolik&migration_status=perform"
    api_headers = {
        "Host": "api.mackolikfeeds.com",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; SM-G991B Build/SP1A.210812.016)",
        "Connection": "Keep-Alive",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "X-Authorization": "token true",
        "X-RequestToken": token,
    }
    try:
        api_response = requests.get(api_url, headers=api_headers)
        api_response.raise_for_status()
        match_details = {}
        response_data = api_response.json()
        for area in response_data.get("data", {}).get("areas", []):
            for competition in area.get("competitions", []):
                for match in competition.get("matches", []):
                    match_id = match.get("id")
                    if match_id and (match.get("hts_A") is not None or match.get("hts_B") is not None):
                        match_details[match_id] = {
                            "hts_A": match.get("hts_A"),
                            "hts_B": match.get("hts_B")
                        }
        return match_details
    except requests.exceptions.RequestException as e:
        print(f"❌ Maç detayları alınırken hata oluştu: {str(e)}")
        return {}

def get_matches_for_date(token: str, date: str) -> List[Dict]:
    api_url = f"https://api.mackolikfeeds.com/betting-service/bulletin/sport/1?date={date}&tz=3&language=tr&real_country=tr&application=com.kokteyl.mackolik&migration_status=perform"
    api_headers = {
        "Host": "api.mackolikfeeds.com",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; SM-G991B Build/SP1A.210812.016)",
        "Connection": "Keep-Alive",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "X-Authorization": "token true",
        "X-RequestToken": token,
    }
    match_parser = MatchData()
    matches = []

    try:
        # İlk API çağrısı - Bahis oranları için
        api_response = requests.get(api_url, headers=api_headers)
        api_response.raise_for_status()
        response_data = api_response.json()

        # İkinci API çağrısı - Maç detayları ve skorlar için
        details_url = f"https://api.mackolikfeeds.com/api/matches/?language=tr&country=tr&add_playing=1&extended_period=1&date={date}&tz=3.0&application=com.kokteyl.mackolik&migration_status=perform"
        details_response = requests.get(details_url, headers=api_headers)
        match_details = {}

        if details_response.status_code == 200:
            details_data = details_response.json()
            
            # Tüm maç detaylarını topla
            for area in details_data.get("data", {}).get("areas", []):
                for competition in area.get("competitions", []):
                    for match in competition.get("matches", []):
                        match_id = match.get("id")
                        if match_id:
                            # Ertelenmiş maçları kontrol et
                            if match.get("status") == "Postponed":
                                continue  # Ertelenmiş maçları atla
                                
                            # API'deki durumu kontrol et - "Played" ise skor içermeli
                            is_played = match.get("status") == "Played"
                            
                            # Maç detaylarını kaydet
                            match_details[match_id] = {
                                "hts_A": match.get("hts_A"),
                                "hts_B": match.get("hts_B"),
                                "fts_A": match.get("fts_A"),  # Skor bilgisi
                                "fts_B": match.get("fts_B"),  # Skor bilgisi
                                "match_time": match.get("match_time"),
                                "time": match.get("time"),
                                "is_played": is_played,  # Oynanmış mı?
                                "status": match.get("status")  # API'den dönen gerçek durum
                            }

        # Her lig için maçları işle
        for area in response_data.get("data", {}).get("soccer", []):
            league_name = area.get("title")
            for match in area.get("matches", []):
                match_id = match.get("id")
                
                # Oran API'sinden gelen durum değeri - Ertelenmiş maçları atla (status=5)
                original_status = match.get("status")
                if original_status == 5:
                    continue  # Ertelenmiş maçları atla
                
                # Status değerini belirle - varsayılan olarak 1 (oynanmamış)
                match["Status"] = 1  
                
                # Eğer detay bilgisi varsa, ana veriyle birleştir
                if match_id in match_details:
                    detail = match_details[match_id]
                    
                    # Detay API'sinden gelen status kontrolü
                    if detail.get("status") == "Postponed":
                        continue  # Ertelenmiş maçları atla
                    
                    # SADECE detay API'si skorlarını kullan
                    match["hts_A"] = detail.get("hts_A")
                    match["hts_B"] = detail.get("hts_B")
                    match["fts_A"] = detail.get("fts_A")
                    match["fts_B"] = detail.get("fts_B")
                    
                    # Eğer detay API'si "Played" diyorsa veya orijinal status 3 ise, oynanmış kabul et
                    if detail.get("is_played") or original_status == 3:
                        match["Status"] = 3  # Oynanmış kabul et
                
                # Maç verisini işle
                match_data = match_parser.parse_match_data(match)
                match_data["Lig"] = league_name
                match_data["Tarih"] = date

                # Saat bilgisini ayarla
                if match_id in match_details:
                    combined_time_data = {
                        "match_time": match_details[match_id].get("match_time"),
                        "time": match_details[match_id].get("time")
                    }
                    match_data["Saat"] = get_match_time(combined_time_data)
                else:
                    match_data["Saat"] = get_match_time({"time": match.get("time")})
                
                matches.append(match_data)

        # Maçları lig ve saate göre sırala
        return sorted(matches, key=lambda x: (x.get("Lig", ""), x.get("Saat", "00:00")))

    except requests.exceptions.RequestException as e:
        print(f"❌ {date} tarihi için hata: {str(e)}")
        return []

def get_match_time(match_data: Dict) -> str:
    """Farklı API yanıtlarından saat bilgisini alır ve Türkiye saatine çevirir"""
    match_time = match_data.get("match_time") or match_data.get("time")
    if match_time:
        try:
            hour, minute = map(int, match_time.split(':'))
            utc_time = datetime.now(timezone.utc).replace(hour=hour, minute=minute)
            turkey_time = utc_time + timedelta(hours=3)
            return turkey_time.strftime("%H:%M")
        except ValueError:
            return "00:00"
    return "00:00"

def load_historic_data(file_path: str) -> Dict:
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"matches": {}}
    except Exception as e:
        print(f"❌ Veri yükleme hatası: {str(e)}")
        return {"matches": {}}

def save_historic_data(data: Dict, file_path: str):
    try:
        if "matches" in data:
            for date in data["matches"]:
                for match in data["matches"][date]:
                    # Saat bilgisini düzeltme (veri tutarlılığı için)
                    if "Saat" in match:
                        match["Saat"] = match["Saat"][:5] if match["Saat"] else "00:00"
                    
                    # Eğer fts_* değerleri varsa, bunlardan skor oluştur (son kontrol)
                    if "Skor" in match and match["Skor"] == "- - -":
                        fts_A = match.get("fts_A")
                        fts_B = match.get("fts_B")
                        if fts_A is not None and fts_B is not None:
                            match["Skor"] = f"{fts_A} - {fts_B}"
                    
                    # Eğer hts_* değerleri varsa, bunlardan ilk yarı skoru oluştur
                    if "İlk Yarı Skoru" in match and match["İlk Yarı Skoru"] == "- - -":
                        hts_A = match.get("hts_A")
                        hts_B = match.get("hts_B")
                        if hts_A is not None and hts_B is not None:
                            match["İlk Yarı Skoru"] = f"{hts_A} - {hts_B}"

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"❌ Veri kaydetme hatası: {str(e)}")

def get_date_range(start_date: str, end_date: str) -> List[str]:
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        date_list = []
        current = start
        while current <= end:
            date_list.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        return date_list
    except Exception as e:
        print(f"❌ Tarih aralığı oluşturma hatası: {str(e)}")
        return []

def show_match_selection_menu(matches_df) -> int:
    if not isinstance(matches_df, pd.DataFrame):
        matches_df = pd.DataFrame(matches_df)
    print("\n📊 Analiz Seçenekleri:")
    print("─" * 30)
    print("1. Tüm maçları analiz et")
    print("2. Tek bir maç seç")
    print("3. Lig bazlı analiz et")
    print("─" * 30)

    while True:
        choice = input("Seçiminiz (1-3): ")
        if choice in ["1", "2", "3"]:
            return int(choice)
        print("❌ Geçersiz seçim! Lütfen 1, 2 veya 3 girin.")

def select_single_match(matches_df: pd.DataFrame) -> pd.DataFrame:
    if matches_df.empty:
        print("❌ Seçilebilecek maç bulunamadı!")
        return pd.DataFrame()

    print("\n📅 Mevcut Maçlar:")
    print("─" * 80)

    active_matches = matches_df[matches_df["Status"] == 1].copy()

    if active_matches.empty:
        print("❌ Aktif maç bulunamadı!")
        return pd.DataFrame()

    grouped_matches = active_matches.groupby('Lig', sort=True)
    match_index = 1
    match_indices = {}

    for lig_name, lig_group in grouped_matches:
        print(f"\n🏆 {lig_name}")
        print("─" * 80)

        sorted_matches = lig_group.sort_values('Saat')

        for _, match in sorted_matches.iterrows():
            match_time = match['Saat'][:5] if match['Saat'] else "00:00"
            match_str = f"{match_index}. {match['Ev Sahibi']} vs {match['Deplasman']} ({match_time})"
            print(match_str)
            match_indices[match_index] = (match.name, lig_name)
            match_index += 1

    print("\n" + "─" * 80)
    print("📌 Birden fazla maç seçmek için numaraları virgülle ayırarak girin (Örnek: 1,3,5)")
    print("📌 Tüm maçları seçmek için 'H' yazın")
    print("📌 Belirli bir ligin tüm maçlarını seçmek için 'L' ve lig numarasını girin (Örnek: L1)")

    while True:
        try:
            choice = input(f"\nMaç numaralarını seçin (1-{len(match_indices)} arası): ").strip().upper()

            if choice == 'H':
                print(f"\n✅ Tüm maçlar seçildi ({len(active_matches)} maç)")
                return active_matches

            if choice.startswith('L'):
                try:
                    lig_num = int(choice[1:])
                    lig_names = sorted(active_matches['Lig'].unique())
                    if 1 <= lig_num <= len(lig_names):
                        selected_lig = lig_names[lig_num - 1]
                        selected_matches = active_matches[active_matches['Lig'] == selected_lig]
                        print(f"\n✅ {selected_lig} ligi maçları seçildi ({len(selected_matches)} maç)")
                        return selected_matches
                    else:
                        print(f"❌ Geçersiz lig numarası! (1-{len(lig_names)} arası girin)")
                        continue
                except ValueError:
                    print("❌ Geçersiz lig seçimi formatı! Örnek: L1")
                    continue

            selections = [int(x.strip()) for x in choice.split(',')]
            valid_selections = []

            for sel in selections:
                if sel in match_indices:
                    valid_selections.append(match_indices[sel][0])
                else:
                    print(f"❌ Geçersiz seçim: {sel}")

            if valid_selections:
                selected_matches = active_matches.loc[valid_selections]
                print(f"\n✅ Seçilen maçlar ({len(selected_matches)} maç):")

                for lig_name, lig_group in selected_matches.groupby('Lig'):
                    print(f"\n🏆 {lig_name}")
                    print("─" * 80)
                    for _, match_data in lig_group.sort_values('Saat').iterrows():
                        match_time = match_data['Saat'][:5] if match_data['Saat'] else "00:00"
                        print(f"   • {match_data['Ev Sahibi']} vs {match_data['Deplasman']} ({match_time})")

                return selected_matches

            else:
                print("❌ Geçerli bir seçim yapılmadı!")

        except ValueError:
            print("❌ Lütfen geçerli bir format kullanın! Örnek: 1,3,5")

def select_league(matches_df: pd.DataFrame) -> pd.DataFrame:
    if matches_df.empty:
        print("❌ Seçilebilecek lig bulunamadı!")
        return pd.DataFrame()

    active_matches = matches_df[matches_df["Status"] == 1]

    if active_matches.empty:
        print("❌ Aktif maç bulunamadı!")
        return pd.DataFrame()

    available_leagues = sorted(active_matches["Lig"].unique())

    print("\n📅 Mevcut Ligler:")
    print("─" * 50)

    for idx, league in enumerate(available_leagues, 1):
        match_count = len(active_matches[active_matches["Lig"] == league])
        print(f"{idx}. {league} ({match_count} maç)")

    print("─" * 50)
    print("📌 Birden fazla lig seçmek için numaraları virgülle ayırarak girin (Örnek: 1,3,5)")
    print("📌 Tüm ligleri seçmek için 'H' yazın")

    while True:
        try:
            choice = input(f"\nLig numaralarını seçin (1-{len(available_leagues)} arası): ").strip().upper()

            if choice == 'H':
                print(f"\n✅ Tüm ligler seçildi ({len(available_leagues)} lig)")
                return active_matches

            selections = [int(x.strip()) for x in choice.split(',')]
            valid_selections = []
            selected_leagues = []

            for sel in selections:
                if 1 <= sel <= len(available_leagues):
                    valid_selections.append(sel - 1)
                    selected_leagues.append(available_leagues[sel - 1])
                else:
                    print(f"❌ Geçersiz seçim: {sel}")

            if valid_selections:
                selected_matches = active_matches[active_matches["Lig"].isin(selected_leagues)]
                print(f"\n✅ Seçilen ligler ({len(selected_leagues)} lig):")
                for league in selected_leagues:
                    league_matches = selected_matches[selected_matches["Lig"] == league]
                    print(f"\n🏆 {league} ({len(league_matches)} maç):")
                    for _, match in league_matches.iterrows():
                        print(f"   • {match['Ev Sahibi']} vs {match['Deplasman']}")
                return selected_matches
            else:
                print("❌ Geçerli bir seçim yapılmadı!")

        except ValueError:
            print("❌ Lütfen geçerli bir format kullanın! Örnek: 1,3,5")

def get_date_range_choice(analysis_date: datetime) -> tuple[datetime, datetime]:
    print("\n📅 Geçmiş maç aralığını seçin:")
    print("─" * 30)
    print("1. 1 günlük analiz")
    print("2. 3 günlük analiz")
    print("3. 5 günlük analiz")
    print("4. 1 haftalık analiz")
    print("5. 1 aylık analiz")
    print("6. 3 aylık analiz")
    print("7. 6 aylık analiz")
    print("8. 1 yıllık analiz")
    print("─" * 30)

    ranges = {
        "1": 1, "2": 3, "3": 5, "4": 7,
        "5": 30, "6": 90, "7": 180, "8": 365
    }

    while True:
        choice = input("Seçiminiz (1-8): ")
        if choice in ranges:
            days = ranges[choice]
            end_date = analysis_date - timedelta(days=1)
            start_date = end_date - timedelta(days=days)
            return start_date, end_date
        print("❌ Geçersiz seçim!")

def find_similar_matches(historical_df: pd.DataFrame, today_df: pd.DataFrame, threshold: float = 0.05) -> List[Dict]:
    similar_matches = []
    historical_df = historical_df.drop_duplicates(subset=["Ev Sahibi", "Deplasman", "Tarih"])
    today_df = today_df.drop_duplicates(subset=["Ev Sahibi", "Deplasman"])

    ht_required_markets = ["İlk Yarı", "IY 1.5", "IY/MS"]
    non_ht_markets = ["Maç Sonucu", "Karşılıklı Gol", "A/U 2.5", "Toplam Gol", "EV 1.5", "DEP 1.5"]

    min_categories = 3
    min_flexible_matches = 3

    print(f"\n📊 Seçilen tarihteki maçların sayısı: {len(today_df)}")
    print(f"📊 Geçmiş maçların sayısı: {len(historical_df)}")

    if len(today_df) == 0 or len(historical_df) == 0:
        return []

    for _, today_match in today_df.iterrows():
        if today_match["Status"] != 1:
            continue

        for _, hist_match in historical_df.iterrows():
            if hist_match["Status"] != 3:
                continue

            odds_comparison = {}
            matched_categories = 0

            for market_type in non_ht_markets:
                market_outcomes = [col for col in today_match.index if col.startswith(market_type)]
                if not market_outcomes:
                    continue

                market_odds = []
                valid_outcomes_count = 0
                total_outcomes_count = 0

                for outcome in market_outcomes:
                    today_odd = today_match.get(outcome, "-")
                    hist_odd = hist_match.get(outcome, "-")

                    try:
                        today_odd = float(today_odd) if today_odd != "-" else None
                        hist_odd = float(hist_odd) if hist_odd != "-" else None

                        if today_odd is not None and hist_odd is not None:
                            total_outcomes_count += 1
                            difference = abs(today_odd - hist_odd)

                            if difference <= threshold:
                                valid_outcomes_count += 1
                                outcome_name = outcome.split('_')[-1]
                                market_odds.append({
                                    'outcome': outcome_name,
                                    'today': today_odd,
                                    'historical': hist_odd,
                                    'difference': round(difference, 2)
                                })

                    except ValueError:
                        continue

                if total_outcomes_count > 0:
                    if valid_outcomes_count == total_outcomes_count:
                        odds_comparison[market_type] = market_odds
                        matched_categories += 1

            if hist_match.get("İlk Yarı Skoru", "-") != "- - -":
                for market_type in ht_required_markets:
                    market_outcomes = [col for col in today_match.index if col.startswith(market_type)]
                    if not market_outcomes:
                        continue

                    market_odds = []
                    valid_outcomes_count = 0
                    total_outcomes_count = 0

                    for outcome in market_outcomes:
                        today_odd = today_match.get(outcome, "-")
                        hist_odd = hist_match.get(outcome, "-")

                        try:
                            today_odd = float(today_odd) if today_odd != "-" else None
                            hist_odd = float(hist_odd) if hist_odd != "-" else None

                            if today_odd is not None and hist_odd is not None:
                                total_outcomes_count += 1
                                difference = abs(today_odd - hist_odd)

                                if difference <= threshold:
                                    valid_outcomes_count += 1
                                    outcome_name = outcome.split('_')[-1]
                                    market_odds.append({
                                        'outcome': outcome_name,
                                        'today': today_odd,
                                        'historical': hist_odd,
                                        'difference': round(difference, 2)
                                    })

                        except ValueError:
                            continue

                    if total_outcomes_count > 0:
                        if market_type == "IY/MS":
                            if valid_outcomes_count >= min_flexible_matches:
                                odds_comparison[market_type] = market_odds
                                matched_categories += 1
                        else:
                            if valid_outcomes_count == total_outcomes_count:
                                odds_comparison[market_type] = market_odds
                                matched_categories += 1

            if matched_categories >= min_categories and odds_comparison:
                match_info = {
                    "Bugünkü Maç": f"{today_match['Ev Sahibi']} vs {today_match['Deplasman']}",
                    "Benzer Geçmiş Maç": f"{hist_match['Ev Sahibi']} vs {hist_match['Deplasman']}",
                    "Geçmiş Maç Tarihi": hist_match["Tarih"],
                    "Geçmiş Maç Ligi": hist_match.get("Lig", "-"),
                    "İlk Yarı Skoru": hist_match.get("İlk Yarı Skoru", "-"),
                    "Geçmiş Maç Skoru": hist_match["Skor"],
                    "Oranlar": odds_comparison,
                    "Eşleşen Kategori Sayısı": matched_categories
                }
                similar_matches.append(match_info)

    similar_matches.sort(key=lambda x: x["Eşleşen Kategori Sayısı"], reverse=True)
    return similar_matches

def save_results_to_file(similar_matches: List[Dict], base_path: str, is_single_match: bool, selected_teams: str = None):
    def convert_score_to_result(home: int, away: int) -> str:
        """Skorları IY/MS formatına çevirir (1, X, 2)"""
        if home > away:
            return "1"
        elif home == away:
            return "X"
        else:
            return "2"

    def parse_score(score_str: str) -> Tuple[int, int]:
        """Skor string'ini parse eder ve (ev sahibi, deplasman) gollerini döner"""
        if not score_str or score_str == "- - -" or "None" in score_str:
            return None, None
        try:
            parts = score_str.replace(" ", "").split("-")
            if len(parts) != 2:
                return None, None
            home = int(parts[0].strip())
            away = int(parts[1].strip())
            return home, away
        except (ValueError, IndexError):
            return None, None

    try:
        if not os.path.exists(base_path):
            os.makedirs(base_path)

        current_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Dosya adını belirle
        if is_single_match and selected_teams:
            teams = selected_teams.replace(' vs ', '_').replace(' ', '_')
            filename = f"Analiz_{teams}_{current_datetime}.txt"
        elif selected_teams and selected_teams.startswith('Lig_'):
            match_count = len(set(match.get('Bugünkü Maç') for match in similar_matches))
            filename = f"Lig_Analizi_{match_count}mac_{current_datetime}.txt"
        else:
            match_count = len(set(match.get('Bugünkü Maç') for match in similar_matches))
            filename = f"Coklu_Analiz_{match_count}mac_{current_datetime}.txt"

        # Dosya adındaki özel karakterleri temizle
        filename = filename.replace(':', '.').replace('/', '_').replace('\\', '_')
        filepath = os.path.join(base_path, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            today_matches = {}
            # Maçları grupla
            for match in similar_matches:
                today_match = match.get('Bugünkü Maç')
                if today_match not in today_matches:
                    today_matches[today_match] = []
                today_matches[today_match].append(match)

            # Her maç için analiz
            for today_match, matches in today_matches.items():
                f.write("─" * 50 + "\n")
                f.write(f"🏟️ Analiz Edilen Maç: {today_match}\n")
                f.write("─" * 50 + "\n")

                market_stats = {}
                outcome_stats = {}
                total_matches = len(matches)

                for match in matches:
                    match_score = match.get('Geçmiş Maç Skoru', '- - -')
                    match_ht_score = match.get('İlk Yarı Skoru', '- - -')
                    
                    for market_type, odds in match.get('Oranlar', {}).items():
                        if market_type not in market_stats:
                            market_stats[market_type] = {'total': 0}
                            outcome_stats[market_type] = {}

                        market_stats[market_type]['total'] += 1

                        for odd in odds:
                            outcome = odd['outcome']
                            if outcome not in outcome_stats[market_type]:
                                outcome_stats[market_type][outcome] = {
                                    'total': 0,
                                    'realized': 0
                                }
                            outcome_stats[market_type][outcome]['total'] += 1

                            try:
                                # Skorları parse et
                                home_goals, away_goals = parse_score(match_score)
                                ht_home, ht_away = parse_score(match_ht_score)

                                # Eğer tam skor geçersizse devam et
                                if home_goals is None or away_goals is None:
                                    continue

                                total_goals = home_goals + away_goals

                                # Market tipine göre işle
                                if market_type in ["İlk Yarı", "IY 1.5", "IY/MS"]:
                                    if ht_home is None or ht_away is None:
                                        continue
                                    ht_total_goals = ht_home + ht_away

                                    if market_type == "İlk Yarı":
                                        ht_result = convert_score_to_result(ht_home, ht_away)
                                        if outcome == ht_result:
                                            outcome_stats[market_type][outcome]['realized'] += 1

                                    elif market_type == "IY 1.5":
                                        if (outcome == "Üst" and ht_total_goals > 1.5) or \
                                           (outcome == "Alt" and ht_total_goals < 1.5):
                                            outcome_stats[market_type][outcome]['realized'] += 1

                                    elif market_type == "IY/MS":
                                        ht_result = convert_score_to_result(ht_home, ht_away)
                                        ft_result = convert_score_to_result(home_goals, away_goals)
                                        actual_result = f"{ht_result}/{ft_result}"
                                        if actual_result == outcome:
                                            outcome_stats[market_type][outcome]['realized'] += 1

                                else:  # İlk yarı skoru gerektirmeyen marketler
                                    if market_type == "Karşılıklı Gol":
                                        both_scored = home_goals > 0 and away_goals > 0
                                        if (outcome == "Var" and both_scored) or \
                                           (outcome == "Yok" and not both_scored):
                                            outcome_stats[market_type][outcome]['realized'] += 1

                                    elif market_type == "A/U 2.5":
                                        if (outcome == "Üst" and total_goals > 2.5) or \
                                           (outcome == "Alt" and total_goals < 2.5):
                                            outcome_stats[market_type][outcome]['realized'] += 1

                                    elif market_type == "Toplam Gol":
                                        if (outcome == "0-1" and total_goals <= 1) or \
                                           (outcome == "2-3" and (total_goals == 2 or total_goals == 3)) or \
                                           (outcome == "4-5" and (total_goals == 4 or total_goals == 5)) or \
                                           (outcome == "6+" and total_goals >= 6):
                                            outcome_stats[market_type][outcome]['realized'] += 1

                                    elif market_type == "EV 1.5":
                                        if (outcome == "Üst" and home_goals > 1.5) or \
                                           (outcome == "Alt" and home_goals < 1.5):
                                            outcome_stats[market_type][outcome]['realized'] += 1

                                    elif market_type == "DEP 1.5":
                                        if (outcome == "Üst" and away_goals > 1.5) or \
                                           (outcome == "Alt" and away_goals < 1.5):
                                            outcome_stats[market_type][outcome]['realized'] += 1

                                    elif market_type == "Maç Sonucu":
                                        ms_result = convert_score_to_result(home_goals, away_goals)
                                        if outcome == ms_result:
                                            outcome_stats[market_type][outcome]['realized'] += 1

                            except Exception as e:
                                continue

                # İstatistikleri yaz
                f.write(f"\n📊 Bulunan Benzer Oranlı Maç Sayısı: {total_matches}\n\n")

                # Marketleri sırala ve yaz
                sorted_markets = sorted(market_stats.items(), key=lambda x: x[1]['total'], reverse=True)

                for market_type, stats in sorted_markets:
                    f.write(f"\n📈 {market_type} İstatistikleri:\n")
                    f.write("─" * 50 + "\n")
                    f.write(f"Toplam Eşleşme: {stats['total']} maç\n")

                    if market_type in outcome_stats:
                        outcomes = []
                        for outcome, stat in outcome_stats[market_type].items():
                            if stat['total'] > 0:
                                percentage = (stat['realized'] / stat['total'] * 100)
                                outcomes.append((outcome, stat, percentage))

                        # Yüzdelere göre sırala
                        sorted_outcomes = sorted(outcomes, key=lambda x: x[2], reverse=True)

                        for outcome, stat, percentage in sorted_outcomes:
                            f.write(f"{outcome}: {stat['realized']}/{stat['total']} (%{percentage:.1f})\n")
                    f.write("\n")

                # Geçmiş maçların detaylarını yaz
                f.write("\n📋 Geçmiş Maçların Detayları\n")
                f.write("─" * 50 + "\n")
                
                for match in matches:
                    raw_date = match.get('Geçmiş Maç Tarihi', '-')
                    formatted_date = "-"
                    if raw_date != "-":
                        try:
                            date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
                            formatted_date = date_obj.strftime("%d.%m.%Y")
                        except:
                            formatted_date = raw_date

                    f.write(f"\n🔄 Geçmiş Maç: {match.get('Benzer Geçmiş Maç', '-')}\n")
                    f.write(f"🏆 Lig: {match.get('Geçmiş Maç Ligi', '-')}\n")
                    f.write(f"📅 Tarih: {formatted_date}\n")
                    f.write(f"📊 Skor: {match.get('Geçmiş Maç Skoru', '-')}\n")
                    f.write(f"⚽ İlk Yarı: {match.get('İlk Yarı Skoru', '-')}\n\n")

                    # Oran detaylarını yaz
                    for market_type, odds in match.get('Oranlar', {}).items():
                        if odds:
                            f.write(f"📈 {market_type} Oranları:\n")
                            f.write("{:<10} {:>10} {:>10} {:>10}\n".format(
                                "Seçenek", "Bugün", "Geçmiş", "Fark"))
                            f.write("─" * 40 + "\n")

                            for odd in odds:
                                if not pd.isna(odd['today']) and not pd.isna(odd['historical']):
                                    f.write("{:<10} {:>10.2f} {:>10.2f} {:>10.2f}\n".format(
                                        odd['outcome'],
                                        odd['today'],
                                        odd['historical'],
                                        odd['difference']
                                    ))
                            f.write("\n")
                    f.write("─" * 50 + "\n")

        print(f"\n✅ Sonuçlar kaydedildi: {filepath}")

    except Exception as e:
        print(f"\n❌ Dosya kaydetme hatası: {str(e)}")

def analyze_matches():
    base_dir, data_dir, analysis_dir = initialize_directories()
    historic_file = os.path.join(data_dir, "historic_matches.json")
    historic_data = load_historic_data(historic_file)

    # datetime.UTC yerine timezone.utc kullanın
    today = datetime.now(timezone.utc)
    print("\n📅 Analiz edilecek günü seçin:")
    print("─" * 30)
    dates = []
    for i in range(5):
        future_date = today + timedelta(days=i)
        if i == 0:
            print(f"{i+1}. Bugün ({future_date.strftime('%d.%m.%Y')})")
        elif i == 1:
            print(f"{i+1}. Yarın ({future_date.strftime('%d.%m.%Y')})")
        else:
            print(f"{i+1}. {future_date.strftime('%d.%m.%Y')}")
        dates.append(future_date)
    print("─" * 30)

    while True:
        try:
            choice = int(input("Seçiminiz (1-5): "))
            if 1 <= choice <= 5:
                analysis_date = dates[choice-1]
                break
            print("❌ Lütfen 1-5 arasında bir sayı girin.")
        except ValueError:
            print("❌ Lütfen geçerli bir sayı girin.")

    print("\n⚽ Analiz edilecek günün maçları alınıyor...")
    token = get_token()
    if token:
        analysis_matches = get_matches_for_date(token, analysis_date.strftime("%Y-%m-%d"))
        analysis_df = pd.DataFrame(analysis_matches)

        if not analysis_df.empty:
            selection_type = show_match_selection_menu(analysis_df)
            selected_teams = None
            is_single_match = False

            if selection_type == 2:
                analysis_df = select_single_match(analysis_df)
                if analysis_df.empty:
                    return
                selected_teams = f"{analysis_df.iloc[0]['Ev Sahibi']} vs {analysis_df.iloc[0]['Deplasman']}"
                is_single_match = True
            elif selection_type == 3:
                analysis_df = select_league(analysis_df)
                if analysis_df.empty:
                    return
                selected_teams = f"Lig_{analysis_df.iloc[0]['Lig'].replace(' ', '_')}"
                is_single_match = False

            start_date, end_date = get_date_range_choice(analysis_date)

            print(f"\n📊 {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')} tarihleri arasındaki maçlar analiz ediliyor...")
            historical_matches = []

            for date in get_date_range(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")):
                if date in historic_data["matches"]:
                    historical_matches.extend(historic_data["matches"][date])
                else:
                    daily_matches = get_matches_for_date(token, date)
                    if daily_matches:
                        historic_data["matches"][date] = daily_matches
                        historical_matches.extend(daily_matches)

            save_historic_data(historic_data, historic_file)
            historical_df = pd.DataFrame(historical_matches)

            print("\n🔍 Benzer maçlar analiz ediliyor...")
    similar_matches = find_similar_matches(historical_df, analysis_df)

    if similar_matches:
        save_results_to_file(similar_matches, analysis_dir, is_single_match, selected_teams)
    else:
        print("\n❌ Benzer Maç Bulunamadı!")

def get_base_directory():
    """Tüm işletim sistemleri için sabit ana dizin yapısı"""
    os_type = platform.system().lower()

    if os_type == "windows":
        return "C:\\Oran Analiz"
    elif "linux" in os_type:
        if os.path.exists("/storage/emulated/0"):
            return "/storage/emulated/0/Oran Analiz"
        else:
            home = os.path.expanduser("~")
            return os.path.join(home, "Oran Analiz")
    else:
        home = os.path.expanduser("~")
        return os.path.join(home, "Oran Analiz")

def initialize_directories() -> tuple:
    """Gerekli dizinleri oluşturur ve dizin yollarını döndürür"""
    try:
        base_dir = get_base_directory()

        if platform.system().lower() == "linux" and "/storage/emulated/0" not in base_dir:
            if os.path.exists("/storage/emulated/0"):
                base_dir = "/storage/emulated/0/Oran Analiz"

        data_dir = os.path.join(base_dir, "Veriler")
        analysis_dir = os.path.join(base_dir, "Analizler")

        for directory in [base_dir, data_dir, analysis_dir]:
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                    print(f"✅ Dizin oluşturuldu: {directory}")
                except Exception as e:
                    print(f"❌ Dizin oluşturulamadı: {directory}")
                    print(f"Hata: {str(e)}")
                    if "permission denied" in str(e).lower():
                        alt_dir = directory.replace(base_dir, "/storage/emulated/0/Oran Analiz")
                        try:
                            os.makedirs(alt_dir)
                            print(f"✅ Alternatif dizin oluşturuldu: {alt_dir}")
                            if directory == base_dir:
                                base_dir = alt_dir
                            elif directory == data_dir:
                                data_dir = alt_dir
                            elif directory == analysis_dir:
                                analysis_dir = alt_dir
                        except Exception as e2:
                            print(f"❌ Alternatif dizin oluşturulamadı: {str(e2)}")

        return base_dir, data_dir, analysis_dir
    except Exception as e:
        print(f"❌ Dizin oluşturma hatası: {str(e)}")

# Global variables
base_dir = None
data_dir = None
analysis_dir = None
historic_data = None

def main():
    global base_dir, data_dir, analysis_dir, historic_data
    
    try:
        # Dizinleri başlat
        base_dir, data_dir, analysis_dir = initialize_directories()
        historic_file = os.path.join(data_dir, "historic_matches.json")
        
        # Program başladığında otomatik güncelleme yap
        print("\n🔄 Otomatik veri güncelleme başlatılıyor...")
        token = get_token()
        if token:
            historic_data = auto_update_data(historic_file)
        else:
            print("❌ Token alınamadı! Güncelleme yapılamadı.")
            historic_data = load_historic_data(historic_file)

        # Ana menüye devam et
        while True:
            print("\n📊 Oran Analiz Ana Menü:")
            print("─" * 30)
            print("1. Maç analizi yap")
            print("2. Çıkış")
            print("─" * 30)

            choice = input("Seçiminiz (1-2): ")

            if choice == "1":
                analyze_matches()
            elif choice == "2":
                print("\n👋 Programdan çıkılıyor...")
                break
            else:
                print("❌ Geçersiz seçim!")

            if choice != "2":
                retry = input("\nYeni bir işlem yapmak ister misiniz? (E/H): ").upper()
                if retry != 'E':
                    print("\n👋 Programdan çıkılıyor...")
                    break

    except Exception as e:
        print(f"\n❌ Program hatası: {str(e)}")
        input("\nProgramı kapatmak için bir tuşa basın...")

if __name__ == "__main__":
    main()