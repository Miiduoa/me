import requests
from bs4 import BeautifulSoup
import logging
import random
from firebase_manager import add_document
from firebase_admin import firestore

logger = logging.getLogger(__name__)

def crawl_movies(limit=10):
    """爬取電影資訊
    
    從熱門電影網站爬取電影數據
    
    Args:
        limit: 最大爬取電影數量
        
    Returns:
        電影列表，每部電影包含標題、海報URL、評分等信息
    """
    try:
        # 這裡使用台灣的 Yahoo 電影或其他電影網站
        url = "https://movies.yahoo.com.tw/movie_intheaters.html"
        
        logger.info(f"開始爬取電影數據: {url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            logger.error(f"爬取失敗，狀態碼: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 找到電影列表
        movie_list = soup.select('.release_info_text')
        
        movies = []
        count = 0
        
        # 如果沒找到電影，返回一些示例電影數據
        if not movie_list:
            logger.warning("沒有找到電影數據，返回示例數據")
            return get_sample_movies()
        
        for movie_div in movie_list:
            if count >= limit:
                break
                
            try:
                # 電影標題
                title_element = movie_div.select_one('.release_movie_name > a')
                title = title_element.text.strip() if title_element else "未知標題"
                
                # 電影簡介
                info_element = movie_div.select_one('.release_text')
                description = info_element.text.strip() if info_element else ""
                
                # 海報URL (從父元素獲取)
                poster_element = movie_div.find_previous('div', class_='release_foto').find('img')
                poster_url = poster_element['src'] if poster_element else ""
                
                # 評分 (隨機生成1-5的評分)
                rating = random.randint(1, 5)
                
                # 上映日期
                date_element = movie_div.select_one('.release_movie_time')
                release_date = date_element.text.replace('上映日期：', '').strip() if date_element else ""
                
                movie = {
                    'title': title,
                    'description': description,
                    'poster_url': poster_url,
                    'rating': rating,
                    'release_date': release_date
                }
                
                movies.append(movie)
                count += 1
                
            except Exception as e:
                logger.error(f"處理電影數據時出錯: {str(e)}")
                continue
        
        logger.info(f"成功爬取 {len(movies)} 部電影")
        return movies
        
    except Exception as e:
        logger.error(f"爬取電影時發生錯誤: {str(e)}")
        # 如果爬取失敗，返回一些示例數據
        return get_sample_movies()

def get_sample_movies():
    """返回示例電影數據"""
    return [
        {
            'title': '蜘蛛人：穿越新宇宙',
            'description': '麥爾斯·莫拉雷斯與朋友們再次展開穿越多重宇宙的冒險...',
            'poster_url': 'https://movies.yahoo.com.tw/i/o/production/movies/June2023/IfWmjVGRlQeJTrxj6Mlj-1080x1539.jpg',
            'rating': 5,
            'release_date': '2023-06-14'
        },
        {
            'title': '奧本海默',
            'description': '由諾蘭執導的傳記片，講述美國物理學家羅伯特·奧本海默的故事...',
            'poster_url': 'https://movies.yahoo.com.tw/i/o/production/movies/July2023/gw82bgMY8Dlm9IqGuOf5-1080x1600.jpg',
            'rating': 4,
            'release_date': '2023-07-21'
        },
        {
            'title': '芭比',
            'description': '芭比娃娃在真實世界中的冒險...',
            'poster_url': 'https://movies.yahoo.com.tw/i/o/production/movies/June2023/Qg8gj3rR1c5U0TLu9jEN-1080x1600.jpg',
            'rating': 4,
            'release_date': '2023-07-20'
        },
        {
            'title': '讀飄',
            'description': '改編自經典小說，講述愛情與生活的故事...',
            'poster_url': 'https://movies.yahoo.com.tw/i/o/production/movies/May2023/xQGrk4iqF89SpDt7ejBk-1080x1510.jpg',
            'rating': 3,
            'release_date': '2023-05-24'
        },
        {
            'title': '大娛樂家',
            'description': 'P.T. 巴納姆的故事，一個夢想家如何創建了世界上最偉大的表演...',
            'poster_url': 'https://movies.yahoo.com.tw/i/o/production/movies/December2022/0T8o3goPnxRF9XnuaNaZ-1080x1517.jpg',
            'rating': 5,
            'release_date': '2022-12-29'
        }
    ]

def crawl_movies_for_firebase():
    """爬取電影資訊並存入Firebase"""
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