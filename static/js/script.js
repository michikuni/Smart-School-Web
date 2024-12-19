function showDate() {
    const now = new Date();
    const day = String(now.getDate()).padStart(2, '0');
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const year = now.getFullYear();
    const formattedDate = `${day}/${month}/${year}`;

    // Hiển thị ngày tháng năm
    document.getElementById('date_title').textContent = formattedDate;
}

// Cập nhật ngày giờ mỗi giây
setInterval(showDate, 1000);
