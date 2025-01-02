document.getElementById('date-form').addEventListener('submit', async function (e) {
    e.preventDefault(); // Ngăn chặn tải lại trang
    const dateInput = document.getElementById('date').value;

    if (!dateInput || isNaN(new Date(dateInput).getTime())) {
        alert('Please select a valid date.');
        return;
    }

    try {
        const response = await fetch('/submit_date', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ date: dateInput })
        });

        if (!response.ok) {
            throw new Error('Failed to fetch data');
        }

        const data = await response.json();
        displayResult(data);
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('result').innerHTML = '<p class="text-danger">Error loading data.</p>';
    }
});

document.getElementById('date').addEventListener('input', function () {
    const dateInput = document.getElementById('date').value;
    const checkoutButton = document.getElementById('checkout-all');

    if (!dateInput) {
        checkoutButton.disabled = true; // Vô hiệu hóa nút nếu không có ngày
        checkoutButton.style.backgroundColor = 'gray'; // Đổi màu nút
        return;
    }

    const selectedDate = new Date(dateInput);
    const currentDate = new Date();

    // Đặt giờ phút giây của ngày hiện tại về 0 để so sánh chỉ ngày
    currentDate.setHours(0, 0, 0, 0);
    selectedDate.setHours(0, 0, 0, 0);

    const differenceInDays = (selectedDate - currentDate) / (1000 * 60 * 60 * 24);

    if (differenceInDays > 1 || differenceInDays < 0) {
        // Nếu ngày được chọn vượt quá 1 ngày hoặc là ngày quá khứ
        checkoutButton.disabled = true;
        checkoutButton.style.backgroundColor = 'gray';
    } else {
        // Ngày hợp lệ trong khoảng 0-1 ngày
        checkoutButton.disabled = false;
        checkoutButton.style.backgroundColor = ''; // Khôi phục màu gốc
    }
});

document.getElementById('checkout-all').addEventListener('click', async function () {
    const dateInputCheckout = document.getElementById('date').value;

    if (!dateInputCheckout || isNaN(new Date(dateInputCheckout).getTime())) {
        alert('Please select a valid date before checking out all.');
        return;
    }

    try {
        const response = await fetch('/checkout_all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dateCheckout: dateInputCheckout })
        });

        if (!response.ok) {
            throw new Error('Failed to send checkout request');
        }

        const result = await response.json();
        alert(result.message || 'Checking out all successfully');
    } catch (error) {
        console.error('Error:', error);
    }
});


function displayResult(data) {
    if (!data || !data.attendance || Object.keys(data.attendance).length === 0) {
        document.getElementById('result').innerHTML = '<p class="text-warning">No data available for the selected date.</p>';
        return;
    }

    let html = `
        <h2 class="my-4">Attendance for ${data.date}</h2>
        <div class="table-responsive">
            <table class="table table-bordered">
                <thead class="table-light">
                    <tr>
                        <th>Mã SV</th>
                        <th>Họ tên</th>
                        <th>Trạng thái điểm danh</th>
                        <th>Thời gian check-in</th>
                        <th>Thời gian check-out</th>
                    </tr>
                </thead>
                <tbody>
    `;
    for (const [ma_sv, record] of Object.entries(data.attendance)) {
        const stateText = record.state === "1" ? "Đã điểm danh" : "Chưa điểm danh";
        html += `
            <tr>
                <td>${ma_sv}</td>
                <td>${record.student_name}</td>
                <td>${stateText || 'N/A'}</td>
                <td>${record.checkin || 'N/A'}</td>
                <td>${record.checkout || 'N/A'}</td>
            </tr>
        `;
    }
    html += `
                </tbody>
            </table>
        </div>
    `;
    document.getElementById('result').innerHTML = html;
}
