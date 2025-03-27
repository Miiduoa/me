import requests
from bs4 import BeautifulSoup
from firebase_manager import add_document

def crawl_movies():
    """爬取電影資訊"""
    url = "https://www.atmovies.com.tw/movie/now/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    response.encoding = "utf-8"
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        movie_list = soup.select("ul.filmListAll li")
        
        movies = []
        for movie in movie_list:
            try:
                # 電影標題
                title_elem = movie.select_one("div.filmtitle a")
                title = title_elem.text.strip() if title_elem else "未知標題"
                
                # 電影連結
                link = "https://www.atmovies.com.tw" + title_elem['href'] if title_elem else ""
                
                # 電影海報
                poster_elem = movie.select_one("img")
                poster = poster_elem['src'] if poster_elem else ""
                
                # 上映日期
                date_elem = movie.select_one("div.runtime span")
                date = date_elem.text.strip() if date_elem else "未知日期"
                
                # 評分
                rating_elem = movie.select_one("div.runtime span.counts")
                rating = rating_elem.text.strip() if rating_elem else "無評分"
                
                movie_data = {
                    "title": title,
                    "link": link,
                    "poster": poster,
                    "date": date,
                    "rating": rating,
                    "crawled_at": firestore.SERVER_TIMESTAMP
                }
                
                # 存入Firebase
                add_document("movies", movie_data)
                movies.append(movie_data)
                
            except Exception as e:
                print(f"處理電影時出錯: {e}")
                continue
        
        return movies
    
    return [] 