(function() {
    console.log("RetainAI Widget Loaded");

    // 1. Get User Configuration or Defaults
    // This allows the client to do: RetainAI.init({ color: '#E50914' })
    let config = {
        color: '#2563EB', // Default Blue
        projectId: 'demo_client_1'
    };

    const container = document.createElement('div');
    container.id = 'retain-ai-container';
    container.style.position = 'fixed';
    container.style.top = '0';
    container.style.left = '0';
    container.style.width = '100vw';
    container.style.height = '100vh';
    container.style.zIndex = '999999';
    container.style.display = 'none';
    
    // Transparent background for the iframe container
    // This lets the client site show through!
    container.style.backgroundColor = 'transparent'; 

    const iframe = document.createElement('iframe');
    iframe.style.width = '100%';
    iframe.style.height = '100%';
    iframe.style.border = 'none';
    
    // IMPORTANT: Make iframe background transparent
    iframe.allowTransparency = "true"; 

    container.appendChild(iframe);
    document.body.appendChild(container);

    window.RetainAI = {
        init: function(userConfig) {
            if (userConfig) {
                config = { ...config, ...userConfig };
            }
            // Update URL with the requested Brand Color
            iframe.src = `https://churnkey-demo.onrender.com/demo?color=${encodeURIComponent(config.color)}`;
        },
        open: function() {
            container.style.display = 'block';
        },
        close: function() {
            container.style.display = 'none';
            // Reload iframe to reset state for next time
            iframe.src = iframe.src; 
        }
    };

    // Default init
    window.RetainAI.init();

    window.addEventListener('message', function(event) {
        if (event.data === 'close-modal') {
            window.RetainAI.close();
        }
    });

})();