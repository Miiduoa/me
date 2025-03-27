document.addEventListener('DOMContentLoaded', function() {
    // 當風格選擇器中的項目被點擊時
    document.querySelectorAll('.style-switcher-item').forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const style = this.dataset.style;
            
            // 發送AJAX請求來更改風格
            fetch(`/set-style/${style}`, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // 重新載入頁面以應用新風格
                    window.location.reload();
                }
            })
            .catch(error => console.error('風格切換錯誤:', error));
        });
    });
}); 