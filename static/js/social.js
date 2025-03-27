document.addEventListener('DOMContentLoaded', function() {
    // 表單驗證
    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(form => {
        form.addEventListener('submit', event => {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });

    // 貼文文本區域自動調整高度
    const postContent = document.getElementById('post-content');
    if (postContent) {
        postContent.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });
    }

    // 圖片上傳預覽
    const imageUploadBtn = document.querySelector('.btn-upload-image');
    const imageInput = document.getElementById('image-upload');
    const imagePreviewContainer = document.getElementById('image-preview');
    
    if (imageUploadBtn && imageInput) {
        imageUploadBtn.addEventListener('click', function() {
            imageInput.click();
        });
        
        imageInput.addEventListener('change', function() {
            if (this.files && this.files[0]) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    // 創建預覽容器
                    imagePreviewContainer.innerHTML = '';
                    imagePreviewContainer.classList.remove('d-none');
                    
                    const previewDiv = document.createElement('div');
                    previewDiv.className = 'position-relative';
                    
                    const img = document.createElement('img');
                    img.src = e.target.result;
                    img.className = 'img-fluid rounded mb-2';
                    img.style.maxHeight = '200px';
                    
                    const removeBtn = document.createElement('button');
                    removeBtn.type = 'button';
                    removeBtn.className = 'btn btn-sm btn-danger position-absolute top-0 end-0 m-1 rounded-circle';
                    removeBtn.innerHTML = '<i class="fas fa-times"></i>';
                    removeBtn.addEventListener('click', function() {
                        imagePreviewContainer.innerHTML = '';
                        imagePreviewContainer.classList.add('d-none');
                        imageInput.value = '';
                    });
                    
                    previewDiv.appendChild(img);
                    previewDiv.appendChild(removeBtn);
                    imagePreviewContainer.appendChild(previewDiv);
                };
                reader.readAsDataURL(this.files[0]);
            }
        });
    }

    // 浮動按鈕滾動效果
    const floatBtn = document.querySelector('.float-btn');
    if (floatBtn) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 300) {
                floatBtn.classList.add('show');
            } else {
                floatBtn.classList.remove('show');
            }
        });
    }

    // 懶加載圖片
    const lazyImages = document.querySelectorAll('.lazy-image');
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver(function(entries, observer) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    const image = entry.target;
                    image.src = image.dataset.src;
                    image.classList.remove('lazy-image');
                    imageObserver.unobserve(image);
                }
            });
        });

        lazyImages.forEach(function(image) {
            imageObserver.observe(image);
        });
    } else {
        // Fallback for browsers without IntersectionObserver support
        lazyImages.forEach(function(image) {
            image.src = image.dataset.src;
            image.classList.remove('lazy-image');
        });
    }
}); 