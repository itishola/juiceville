const CACHE_NAME = 'juiceville-v1.3';
const urlsToCache = [
    '/',
    '/static/orders/css/bootstrap.min.css',
    '/static/orders/css/style.css',
    '/static/orders/css/mobile-responsive.css',
    '/static/orders/js/mobile-responsive.js',
    '/static/orders/img/favicon.ico',
    '/static/orders/img/apple-touch-icon.png',
    '/offline/'
];

// Install event - cache essential files
self.addEventListener('install', function(event) {
    console.log('Service Worker installing.');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(function(cache) {
                console.log('Opened cache');
                return cache.addAll(urlsToCache);
            })
            .then(() => self.skipWaiting())
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', function(event) {
    console.log('Service Worker activating.');
    event.waitUntil(
        caches.keys().then(function(cacheNames) {
            return Promise.all(
                cacheNames.map(function(cacheName) {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch event - serve from cache when offline
self.addEventListener('fetch', function(event) {
    // Skip non-GET requests and external URLs
    if (event.request.method !== 'GET' || 
        !event.request.url.startsWith(self.location.origin)) {
        return;
    }

    event.respondWith(
        caches.match(event.request)
            .then(function(response) {
                // Cache hit - return response
                if (response) {
                    return response;
                }

                // Clone the request
                const fetchRequest = event.request.clone();

                return fetch(fetchRequest).then(
                    function(response) {
                        // Check if valid response
                        if(!response || response.status !== 200 || response.type !== 'basic') {
                            return response;
                        }

                        // Clone the response
                        const responseToCache = response.clone();

                        caches.open(CACHE_NAME)
                            .then(function(cache) {
                                // Cache new requests for static assets
                                if (event.request.url.match(/\.(css|js|png|jpg|jpeg|gif|ico|woff|woff2|ttf|eot|svg)$/)) {
                                    cache.put(event.request, responseToCache);
                                }
                            });

                        return response;
                    }
                ).catch(function() {
                    // If fetch fails and it's a navigation request, show offline page
                    if (event.request.mode === 'navigate') {
                        return caches.match('/offline/');
                    }
                    
                    // For other requests, you might want to return a fallback
                    return new Response('Network error happened', {
                        status: 408,
                        headers: { 'Content-Type': 'text/plain' }
                    });
                });
            }
        )
    );
});

// Background sync for offline orders
self.addEventListener('sync', function(event) {
    if (event.tag === 'background-sync') {
        console.log('Background sync triggered');
        event.waitUntil(doBackgroundSync());
    }
});

async function doBackgroundSync() {
    // You can implement background sync for offline orders here
    console.log('Performing background sync...');
}