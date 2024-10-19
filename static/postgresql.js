/* static/postgresql.js */

document.addEventListener('DOMContentLoaded', function () {
    const tableSelect = document.getElementById('table');
    const columnsDiv = document.getElementById('columns');
    const selectAllCheckbox = document.getElementById('selectAll');
    const queryForm = document.getElementById('queryForm');
    const customQueryForm = document.getElementById('customQueryForm');
    const downloadCsvButton = document.getElementById('downloadCsv');
    const resultsDiv = document.getElementById('results');

    // Fetch tables
    fetch('/get_postgresql_tables')
        .then(response => response.json())
        .then(tables => {
            tables.forEach(table => {
                const option = document.createElement('option');
                option.value = table;
                option.textContent = table;
                tableSelect.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error fetching tables:', error);
            alert('Error fetching tables. Please try again later.');
        });

    // Fetch columns when table is selected
    tableSelect.addEventListener('change', function() {
        columnsDiv.innerHTML = '';
        selectAllCheckbox.checked = false;
        if (this.value) {
            fetch(`/get_postgresql_columns?table=${encodeURIComponent(this.value)}`)
                .then(response => response.json())
                .then(columns => {
                    columns.forEach(column => {
                        const div = document.createElement('div');
                        div.classList.add('flex', 'items-center');
                        div.innerHTML = `
                            <input type="checkbox" id="${column}" name="columns" value="${column}" class="mr-2">
                            <label for="${column}" class="text-sm text-gray-700">${column}</label>
                        `;
                        columnsDiv.appendChild(div);
                    });
                })
                .catch(error => {
                    console.error('Error fetching columns:', error);
                    alert('Error fetching columns. Please try again later.');
                });
        }
    });

    // Handle select all checkbox
    selectAllCheckbox.addEventListener('change', function() {
        const checkboxes = columnsDiv.querySelectorAll('input[type="checkbox"]');
        checkboxes.forEach(checkbox => checkbox.checked = this.checked);
    });

    // Handle query form submission
    queryForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const selectedColumns = Array.from(columnsDiv.querySelectorAll('input[type="checkbox"]:checked')).map(cb => cb.value);
        if (!tableSelect.value || selectedColumns.length === 0) {
            alert("Please select a table and at least one column.");
            return;
        }
        const data = {
            table: tableSelect.value,
            columns: selectedColumns,
            limit: document.getElementById('limit').value
        };

        // Show loading indicator
        resultsDiv.innerHTML = '<p class="text-gray-600">Loading...</p>';

        fetch('/execute_postgresql_query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data),
        })
        .then(response => response.json())
        .then(results => displayResults(results))
        .catch(error => {
            console.error('Error executing query:', error);
            resultsDiv.innerHTML = '<p class="text-red-500">Error executing query. Please try again.</p>';
        });
    });

    // Handle custom query form submission
    customQueryForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const query = document.getElementById('customQuery').value.trim();
        if (!query) {
            alert('Please enter a query.');
            return;
        }
        const data = {
            query: query,
            source: 'postgresql'
        };

        // Show loading indicator
        resultsDiv.innerHTML = '<p class="text-gray-600">Loading...</p>';

        fetch('/execute_custom_query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data),
        })
        .then(response => response.json())
        .then(results => displayResults(results))
        .catch(error => {
            console.error('Error executing custom query:', error);
            resultsDiv.innerHTML = '<p class="text-red-500">Error executing query. Please try again.</p>';
        });
    });

    // Handle CSV download
    downloadCsvButton.addEventListener('click', function() {
        const selectedColumns = Array.from(columnsDiv.querySelectorAll('input[type="checkbox"]:checked')).map(cb => cb.value);
        if (!tableSelect.value || selectedColumns.length === 0) {
            alert("Please select a table and at least one column.");
            return;
        }
        const data = {
            table: tableSelect.value,
            columns: selectedColumns,
            limit: document.getElementById('limit').value,
            source: 'postgresql'
        };

        fetch('/download_csv', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data),
        })
        .then(response => {
            if (response.ok) {
                return response.blob();
            } else {
                return response.json().then(err => { throw err; });
            }
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = 'query_results.csv';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
        })
        .catch(error => {
            console.error('Error downloading CSV:', error);
            alert('Error downloading CSV: ' + (error.error || 'Unknown error'));
        });
    });

    // Function to display results
    function displayResults(results) {
        if (results.error) {
            resultsDiv.innerHTML = `<p class="text-red-500">Error: ${results.error}</p>`;
            return;
        }
        if (results.length === 0) {
            resultsDiv.innerHTML = '<p class="text-gray-600">No results found.</p>';
            return;
        }

        let tableHtml = '<div class="table-responsive"><table class="table-auto"><thead><tr>';

        // Create table headers
        for (const key in results[0]) {
            tableHtml += `<th>${key}</th>`;
        }
        tableHtml += '</tr></thead><tbody>';

        // Create table rows
        results.forEach((row, index) => {
            tableHtml += `<tr>`;
            for (const key in row) {
                tableHtml += `<td>${row[key]}</td>`;
            }
            tableHtml += '</tr>';
        });

        tableHtml += '</tbody></table></div>';
        resultsDiv.innerHTML = tableHtml;
    }
});
