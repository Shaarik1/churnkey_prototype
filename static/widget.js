(function() {
    console.log("RetainAI Widget Loaded");

    // 1. Configuration
    const CONFIG = {
        // This points to YOUR Render URL
        iframeUrl: "https://churnkey-demo.onrender.com/demo", 
        // In a real app, this would be passed by the client
        projectId: document.currentScript.getAttribute('data-project-id') || 'demo_client_1'
    };

    // 2. Create the Modal Container (Hidden by default)
    const container = document.createElement('div');
    container.id = 'retain-ai-container';
    container.style.position = 'fixed';
    container.style.top = '0';
    container.style.left = '0';
    container.style.width = '100vw';
    container.style.height = '100vh';
    container.style.zIndex = '999999'; // On top of everything
    container.style.display = 'none'; // Hidden initially
    container.style.backgroundColor = 'rgba(0,0,0,0.5)'; // Dim background

    // 3. Create the Iframe
    const iframe = document.createElement('iframe');
    iframe.src = CONFIG.iframeUrl;
    iframe.style.width = '100%';
    iframe.style.height = '100%';
    iframe.style.border = 'none';
    iframe.style.background = 'transparent';
    
    container.appendChild(iframe);
    document.body.appendChild(container);

    // 4. The Public API (How the client triggers it)
    window.RetainAI = {
        open: function() {
            container.style.display = 'block';
        },
        close: function() {
            container.style.display = 'none';
        }
    };

    // 5. Listen for "Close" messages from inside the iframe
    window.addEventListener('message', function(event) {
        if (event.data === 'close-modal') {
            window.RetainAI.close();
        }
    });

})();