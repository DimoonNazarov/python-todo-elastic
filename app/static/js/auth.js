/**
 * Обновление access токена через refresh токен (из httpOnly cookie)
 */
async function refreshAccessToken() {
    try {
        const response = await fetch('/auth/refresh', {
            method: 'POST',
            credentials: 'same-origin'
        });

        if (!response.ok) {
            throw new Error('Failed to refresh token');
        }

        return true; // куки обновились на сервере, этого достаточно
    } catch (error) {
        console.error('Token refresh failed:', error);
        window.location.href = '/auth/login';
        return false;
    }
}

/**
 * fetch с автоматическим обновлением токена при 401.
 * Используй вместо обычного fetch() везде, где нужна авторизация.
 */
function cloneRequestBody(body) {
    if (!body) {
        return body;
    }

    if (body instanceof FormData) {
        const cloned = new FormData();
        for (const [key, value] of body.entries()) {
            cloned.append(key, value);
        }
        return cloned;
    }

    if (body instanceof URLSearchParams) {
        return new URLSearchParams(body.toString());
    }

    if (typeof body === 'string') {
        return body;
    }

    return body;
}

async function fetchWithAuth(url, options = {}) {
    const requestOptions = {
        ...options,
        body: cloneRequestBody(options.body),
        credentials: 'same-origin'
    };

    let response = await fetch(url, requestOptions);

    if (response.status === 401) {
        const refreshed = await refreshAccessToken();

        if (refreshed) {
            response = await fetch(url, {
                ...options,
                body: cloneRequestBody(options.body),
                credentials: 'same-origin'
            });
        }
    }

    return response;
}
