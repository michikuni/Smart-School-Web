// Khởi tạo kết nối Socket.IO
const socket = io();

document.getElementById('date-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    const dateInput = document.getElementById('date').value;

    if (!dateInput || isNaN(new Date(dateInput).getTime())) {
        alert('Please select a valid date.');
        return;
    }

    await fetchAndUpdateData(dateInput);
});

// Lắng nghe sự kiện cập nhật từ database
socket.on('database_update', function(data) {
    const dateInput = document.getElementById('date').value;
    if (dateInput) {
        const formattedDate = new Date(dateInput).toLocaleDateString('vi-VN', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        }).split('/').join('-');
        
        if (data.path.includes(formattedDate)) {
            fetchAndUpdateData(dateInput);
        }
    }
});

// Lắng nghe sự kiện cập nhật dữ liệu mới
socket.on('data_update', function(data) {
    const dateInput = document.getElementById('date').value;
    if (dateInput) {
        const formattedDate = new Date(dateInput).toLocaleDateString('vi-VN', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        }).split('/').join('-');
        
        if (data.date === formattedDate) {
            fetchAndUpdateData(dateInput);
        }
    }
});

// Lắng nghe sự kiện checkout all
socket.on('checkout_update', function(data) {
    if (data.success) {
        alert('All students have been checked out successfully');
        const dateInput = document.getElementById('date').value;
        if (dateInput) {
            fetchAndUpdateData(dateInput);
        }
    }
});

document.getElementById('date').addEventListener('input', function () {
    const dateInput = document.getElementById('date').value;
    const checkoutButton = document.getElementById('checkout-all');

    if (!dateInput) {
        checkoutButton.disabled = true;
        checkoutButton.style.backgroundColor = 'gray';
        return;
    }

    const selectedDate = new Date(dateInput);
    const currentDate = new Date();

    currentDate.setHours(0, 0, 0, 0);
    selectedDate.setHours(0, 0, 0, 0);

    const differenceInDays = (selectedDate - currentDate) / (1000 * 60 * 60 * 24);

    if (differenceInDays > 1 || differenceInDays < 0) {
        checkoutButton.disabled = true;
        checkoutButton.style.backgroundColor = 'gray';
    } else {
        checkoutButton.disabled = false;
        checkoutButton.style.backgroundColor = '';
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
        alert(result.message);
    } catch (error) {
        console.error('Error:', error);
        alert('Error processing checkout request');
    }
});

async function fetchAndUpdateData(date) {
    try {
        const response = await fetch('/submit_date', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ date: date })
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
}

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