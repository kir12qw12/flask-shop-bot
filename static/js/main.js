document.addEventListener('DOMContentLoaded', () => {
  // Добавление комментария через fetch
  document.querySelectorAll('.comment-form').forEach(form => {
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const reviewId = form.dataset.review;
      const formData = new FormData(form);
      const res = await fetch(`/reviews/${reviewId}/comment`, {
        method: 'POST',
        body: JSON.stringify(Object.fromEntries(formData)),
        headers: { 'Content-Type': 'application/json' }
      });
      if(res.ok) location.reload(); // после добавления перезагружаем
    });
  });

  // Добавление отзыва через fetch
  const reviewForm = document.getElementById('review-form');
  if(reviewForm) {
    reviewForm.addEventListener('submit', async e => {
      e.preventDefault();
      const formData = new FormData(reviewForm);
      const res = await fetch('/reviews', {
        method: 'POST',
        body: JSON.stringify(Object.fromEntries(formData)),
        headers: { 'Content-Type': 'application/json' }
      });
      if(res.ok) location.reload();
    });
  }

  // Заказ товара с количеством упаковок
  const orderForm = document.getElementById('orderForm');
  if(orderForm) {
    orderForm.addEventListener('submit', async e => {
      e.preventDefault();
      const form = e.target;
      const data = {
        product_id: parseInt(form.dataset.productId),
        weight: parseInt(form.weight.value),
        name: form.name.value,
        phone: form.phone.value,
        comment: form.comment.value,
        quantity: parseInt(form.quantity.value || 1)
      };
      const res = await fetch('/api/order', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(data)
      });
      const json = await res.json();
      if(json.status==='ok'){
        alert(`✅ Заказ отправлен! (${data.quantity} упаковок)`);
        form.reset();
      } else {
        alert('❌ Ошибка при заказе');
      }
    });
  }

  // Добавление в корзину с количеством упаковок
  const addToCartBtn = document.getElementById('addToCartBtn');
  if(addToCartBtn) {
    addToCartBtn.addEventListener('click', () => {
      const productId = parseInt(addToCartBtn.dataset.productId);
      const weight = parseInt(document.getElementById('weightSelect').value);
      const quantity = parseInt(document.getElementById('quantityInput').value || 1);

      let cart = JSON.parse(localStorage.getItem('cart') || '[]');
      cart.push({ product_id: productId, weight, quantity });
      localStorage.setItem('cart', JSON.stringify(cart));
      alert(`✅ Товар добавлен в корзину (${quantity} упаковок)!`);
    });
  }
});
