/* static/payslip.js */

document.addEventListener('DOMContentLoaded', function () {
    const payslipForm = document.getElementById('payslipForm');
    const submitButton = payslipForm.querySelector('button[type="submit"]');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const payslipPreview = document.getElementById('payslipPreview');
    const payslipIframe = document.getElementById('payslipIframe');

    payslipForm.addEventListener('submit', function (event) {
        event.preventDefault();

        const formData = new FormData(payslipForm);

        // Show loading indicator and disable submit button
        loadingIndicator.classList.remove('hidden');
        submitButton.disabled = true;

        fetch('/payslip', {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        })
        .then(response => {
            if (response.ok) {
                return response.blob();
            } else {
                // Handle errors
                return response.json().then(err => { throw err; });
            }
        })
        .then(blob => {
            // Hide loading indicator
            loadingIndicator.classList.add('hidden');
            submitButton.disabled = false;

            // Create a URL for the blob
            const url = window.URL.createObjectURL(blob);

            // Set the iframe src to the blob URL
            payslipIframe.src = url;

            // Show the payslip preview
            payslipPreview.classList.remove('hidden');
        })
        .catch(error => {
            console.error('Error generating payslip:', error);
            alert('Error generating payslip: ' + (error.error || 'Unknown error'));

            // Hide loading indicator and enable submit button
            loadingIndicator.classList.add('hidden');
            submitButton.disabled = false;
        });
    });
});
