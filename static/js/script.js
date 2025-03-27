// 等待DOM完成加載
document.addEventListener('DOMContentLoaded', function() {
    // 添加淡入效果到主要內容
    const mainContent = document.querySelector('main');
    if (mainContent) {
        mainContent.classList.add('fade-in');
    }
    
    // 激活當前頁面的導航項目
    activateCurrentNavItem();
    
    // 添加卡片懸停效果
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-5px)';
            this.style.boxShadow = '0 0.5rem 1rem rgba(0, 0, 0, 0.15)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = '0 0.125rem 0.25rem rgba(0, 0, 0, 0.075)';
        });
    });
    
    // 平滑滾動
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            
            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });
    
    // 防止表單重複提交
    preventDoubleSubmission();
    
    // 添加確認對話框
    document.querySelectorAll('.confirm-action').forEach(element => {
        element.addEventListener('click', function(e) {
            if (!confirm('確定要執行此操作嗎？')) {
                e.preventDefault();
            }
        });
    });
});

// 激活當前頁面的導航項目
function activateCurrentNavItem() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
    
    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPath || 
            (href !== '/' && currentPath.startsWith(href))) {
            link.classList.add('active');
        }
    });
}

// 防止表單重複提交
function preventDoubleSubmission() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            // 獲取提交按鈕
            const submitButtons = this.querySelectorAll('button[type="submit"]');
            
            submitButtons.forEach(button => {
                if (button.classList.contains('btn-processing')) {
                    // 如果按鈕已經處於處理狀態，阻止再次提交
                    e.preventDefault();
                    return;
                }
                
                // 添加處理中狀態
                button.classList.add('btn-processing');
                
                // 備份原始文本
                const originalText = button.innerHTML;
                
                // 更改按鈕文本和外觀
                button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> 處理中...';
                button.disabled = true;
                
                // 設置超時以防止永久禁用
                setTimeout(() => {
                    button.innerHTML = originalText;
                    button.disabled = false;
                    button.classList.remove('btn-processing');
                }, 5000); // 5秒後復原，避免永久禁用
            });
        });
    });
} 