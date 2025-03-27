// CineSocial 互動功能

document.addEventListener('DOMContentLoaded', function() {
    // 點讚功能
    document.querySelectorAll('.post-actions button:first-child').forEach(button => {
        button.addEventListener('click', function() {
            const heartIcon = this.querySelector('i');
            if (heartIcon.classList.contains('far')) {
                heartIcon.classList.replace('far', 'fas');
                this.classList.add('text-danger');
            } else {
                heartIcon.classList.replace('fas', 'far');
                this.classList.remove('text-danger');
            }
        });
    });

    // 發布貼文表單處理
    const postForm = document.querySelector('form[action="/create-post"]');
    if (postForm) {
        postForm.addEventListener('submit', function(e) {
            const textarea = this.querySelector('textarea');
            if (!textarea.value.trim()) {
                e.preventDefault();
                alert('請輸入貼文內容！');
            }
        });
    }

    // 響應式調整
    function adjustLayout() {
        const windowWidth = window.innerWidth;
        const sidebarItems = document.querySelectorAll('.cinesocial-sidebar .nav-link span');
        
        if (windowWidth < 992) {
            sidebarItems.forEach(item => item.style.display = 'none');
        } else {
            sidebarItems.forEach(item => item.style.display = 'block');
        }
    }

    // 初始調整和窗口大小變化時調整
    adjustLayout();
    window.addEventListener('resize', adjustLayout);
}); 