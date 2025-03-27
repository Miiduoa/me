const functions = require('firebase-functions');
const admin = require('firebase-admin');
const fetch = require('node-fetch');
const cheerio = require('cheerio');

admin.initializeApp();

exports.scheduledMovieUpdate = functions.pubsub.schedule('0 0 * * *').onRun(async (context) => {
  console.log('開始每日電影更新');
  
  try {
    // 爬取電影資料的邏輯
    const response = await fetch('https://www.example.com/movies');
    const html = await response.text();
    const $ = cheerio.load(html);
    
    const movies = [];
    
    // 假設的爬蟲邏輯
    $('.movie-item').each((i, elem) => {
      const title = $(elem).find('.title').text().trim();
      const rating = $(elem).find('.rating').text().trim();
      const date = $(elem).find('.date').text().trim();
      
      movies.push({
        title,
        rating,
        date,
        updated_at: admin.firestore.FieldValue.serverTimestamp()
      });
    });
    
    // 批量更新電影資料
    const db = admin.firestore();
    const batch = db.batch();
    
    movies.forEach((movie) => {
      // 使用電影標題作為ID或生成新ID
      const movieRef = db.collection('movies').doc();
      batch.set(movieRef, movie);
    });
    
    await batch.commit();
    console.log(`成功更新 ${movies.length} 部電影`);
    
    return null;
  } catch (error) {
    console.error('電影更新失敗:', error);
    return null;
  }
});

// 創建電影觀看統計數據
exports.trackMovieView = functions.https.onCall((data, context) => {
  // 確保用戶已登入
  if (!context.auth) {
    throw new functions.https.HttpsError('unauthenticated', '必須登入才能追蹤觀看數據');
  }
  
  const { movieId } = data;
  const userId = context.auth.uid;
  
  const db = admin.firestore();
  
  // 記錄用戶查看電影的動作
  return db.collection('user_actions').add({
    type: 'view',
    user_id: userId,
    movie_id: movieId,
    timestamp: admin.firestore.FieldValue.serverTimestamp()
  }).then(() => {
    // 更新電影的查看計數
    return db.collection('movies').doc(movieId).update({
      view_count: admin.firestore.FieldValue.increment(1)
    });
  });
});

// 更新電影排行榜
exports.updateMovieRankings = functions.firestore
    .document('likes/{likeId}')
    .onWrite((change, context) => {
        const db = admin.firestore();
        
        // 獲取所有電影
        return db.collection('movies').get().then(snapshot => {
            const movies = [];
            
            // 為每部電影計算評分並統計喜歡數
            const promises = snapshot.docs.map(doc => {
                const movieId = doc.id;
                const movieData = doc.data();
                
                // 獲取喜歡數
                return db.collection('likes')
                    .where('movie_id', '==', movieId)
                    .get()
                    .then(likesSnapshot => {
                        const likesCount = likesSnapshot.size;
                        
                        // 計算綜合評分 (50%評分 + 50%喜歡)
                        const rating = parseFloat(movieData.rating) || 0;
                        const normalizedLikes = Math.min(likesCount / 10, 10); // 最高10分
                        const compositeScore = (rating * 0.5) + (normalizedLikes * 0.5);
                        
                        movies.push({
                            id: movieId,
                            title: movieData.title,
                            rating: rating,
                            likes: likesCount,
                            score: compositeScore
                        });
                    });
            });
            
            return Promise.all(promises).then(() => {
                // 根據綜合評分排序
                movies.sort((a, b) => b.score - a.score);
                
                // 更新排行榜集合
                const batch = db.batch();
                
                // 刪除舊排行榜
                return db.collection('rankings').doc('movies').delete()
                    .then(() => {
                        // 創建新排行榜
                        batch.set(db.collection('rankings').doc('movies'), {
                            updatedAt: admin.firestore.FieldValue.serverTimestamp(),
                            movies: movies.slice(0, 20) // 取前20名
                        });
                        
                        return batch.commit();
                    });
            });
        });
    });

// 用戶活動分析
exports.analyzeUserActivity = functions.pubsub.schedule('0 1 * * *').onRun(async (context) => {
    const db = admin.firestore();
    
    // 獲取昨天的日期
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const startTimestamp = admin.firestore.Timestamp.fromDate(new Date(yesterday.setHours(0, 0, 0, 0)));
    const endTimestamp = admin.firestore.Timestamp.fromDate(new Date(yesterday.setHours(23, 59, 59, 999)));
    
    // 獲取昨天的用戶操作
    const actionsSnapshot = await db.collection('user_actions')
        .where('timestamp', '>=', startTimestamp)
        .where('timestamp', '<=', endTimestamp)
        .get();
    
    // 統計數據
    const stats = {
        totalViews: 0,
        uniqueUsers: new Set(),
        movieViews: {},
        hourlyActivity: Array(24).fill(0)
    };
    
    actionsSnapshot.forEach(doc => {
        const action = doc.data();
        
        if (action.type === 'view') {
            stats.totalViews++;
            stats.uniqueUsers.add(action.user_id);
            
            // 記錄電影觀看次數
            const movieId = action.movie_id;
            stats.movieViews[movieId] = (stats.movieViews[movieId] || 0) + 1;
            
            // 記錄每小時活動
            if (action.timestamp) {
                const hour = action.timestamp.toDate().getHours();
                stats.hourlyActivity[hour]++;
            }
        }
    });
    
    // 最受歡迎的電影
    const sortedMovies = Object.entries(stats.movieViews)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(async ([movieId, views]) => {
            const movieDoc = await db.collection('movies').doc(movieId).get();
            const movieData = movieDoc.data() || {};
            return {
                id: movieId,
                title: movieData.title || 'Unknown',
                views: views
            };
        });
    
    const topMovies = await Promise.all(sortedMovies);
    
    // 保存分析結果
    const date = yesterday.toISOString().split('T')[0];
    await db.collection('analytics').doc(`daily_${date}`).set({
        date: date,
        totalViews: stats.totalViews,
        uniqueUsers: stats.uniqueUsers.size,
        topMovies: topMovies,
        hourlyActivity: stats.hourlyActivity,
        timestamp: admin.firestore.FieldValue.serverTimestamp()
    });
    
    return null;
}); 