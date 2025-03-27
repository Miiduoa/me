// 主要JavaScript功能檔案

// 當文檔載入完成後執行
document.addEventListener('DOMContentLoaded', function() {
    console.log('網站腳本已載入');
    
    // 啟用所有工具提示
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // 電影卡片懸停效果
    const movieCards = document.querySelectorAll('.movie-card');
    movieCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.classList.add('movie-card-hover');
        });
        card.addEventListener('mouseleave', function() {
            this.classList.remove('movie-card-hover');
        });
    });
    
    // 點讚按鈕處理
    const likeButtons = document.querySelectorAll('.like-button');
    likeButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const movieId = this.getAttribute('data-movie-id');
            const likeCountElement = document.getElementById(`like-count-${movieId}`);
            
            // 發送AJAX請求處理點讚
            fetch(`/movie/${movieId}/like`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // 更新UI
                    if (data.action === 'liked') {
                        this.classList.add('liked');
                        this.querySelector('i').classList.remove('far');
                        this.querySelector('i').classList.add('fas');
                    } else {
                        this.classList.remove('liked');
                        this.querySelector('i').classList.remove('fas');
                        this.querySelector('i').classList.add('far');
                    }
                    
                    // 更新計數
                    if (likeCountElement) {
                        likeCountElement.textContent = data.likes_count;
                    }
                }
            })
            .catch(error => {
                console.error('點讚操作失敗:', error);
            });
        });
    });
});

// 禁用表單的搜尋提交
function disableSearchOnSubmit() {
    const form = document.getElementById('search-form');
    if (form) {
        form.addEventListener('submit', function(e) {
            const searchInput = document.getElementById('search-input');
            if (searchInput && searchInput.value.trim() === '') {
                e.preventDefault();
            }
        });
    }
}

// 平滑滾動到頂部
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
} 