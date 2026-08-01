import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
import api

client = TestClient(api.app)

def test_get_genre_ids_from_names():
    ids = api.get_genre_ids_from_names(["Action", "Sci-Fi", "NonExistentGenre"])
    assert ids == [28, 878]

def test_extract_filters_from_text():
    text = "sci-fi action movies from 2015 to 2020 with rating above 7"
    filters = api.extract_filters_from_text(text)
    
    assert "genres" in filters
    assert set(filters["genres"]) == {"Sci-Fi", "Action"}
    assert filters["year_min"] == 2015
    assert filters["year_max"] == 2020
    assert filters["rating_min"] == 7.0

def test_extract_filters_with_cast_and_director():
    text = "Drama starring Tom Hanks directed by Steven Spielberg"
    filters = api.extract_filters_from_text(text)
    
    assert "genres" in filters
    assert "Drama" in filters["genres"]
    assert filters.get("cast") == "Tom Hanks"
    assert filters.get("director") == "Steven Spielberg"

def test_advanced_search_without_tmdb_key():
    with patch.object(api, "TMDB_API_KEY", None):
        response = client.get("/api/movies/advanced-search?genres=Action&year_min=2010")
        assert response.status_code == 200
        data = response.json()
        assert data["search_results"] == []
        assert data["recommendations"] == []
        assert data["total_results"] == 0
        assert data["filters_used"]["genres"] == ["Action"]
        assert data["filters_used"]["year_min"] == 2010

@pytest.mark.asyncio
async def test_advanced_search_with_mocked_tmdb():
    mock_search_data = {
        "results": [
            {
                "id": 101,
                "title": "Inception",
                "release_date": "2010-07-16",
                "overview": "A thief who steals corporate secrets...",
                "vote_average": 8.4,
                "genre_ids": [28, 878],
                "poster_path": "/inception.jpg"
            }
        ]
    }
    mock_recs_data = [
        {
            "id": 102,
            "name": "Interstellar",
            "year": 2014,
            "category": "TMDB",
            "genre": "Sci-Fi",
            "rating": 8.6,
            "description": "Exploration",
            "poster_url": "https://image.tmdb.org/t/p/w500/interstellar.jpg"
        }
    ]

    with patch.object(api, "TMDB_API_KEY", "fake_key"):
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_search_data
            mock_get.return_value = mock_resp

            with patch("api.tmdb_get_recommendations", new_callable=AsyncMock) as mock_recs:
                mock_recs.return_value = mock_recs_data

                response = client.get("/api/movies/advanced-search?genres=Sci-Fi&year_min=2010&rating_min=8.0")
                assert response.status_code == 200
                data = response.json()
                assert len(data["search_results"]) == 1
                assert data["search_results"][0]["name"] == "Inception"
                assert data["search_results"][0]["year"] == 2010
                assert len(data["recommendations"]) == 1
                assert data["recommendations"][0]["name"] == "Interstellar"

def test_smart_search_endpoint():
    with patch.object(api, "TMDB_API_KEY", None):
        # Test JSON body request
        response = client.post("/api/movies/smart-search", json={"search_query": "action movies from 2020 with rating above 8"})
        assert response.status_code == 200
        data = response.json()
        assert data["filters_used"]["genres"] == ["Action"]
        assert data["filters_used"]["year_min"] == 2020
        assert data["filters_used"]["rating_min"] == 8.0

        # Test query parameter request
        response = client.post("/api/movies/smart-search?search_query=comedy movies from 2018")
        assert response.status_code == 200
        data = response.json()
        assert data["filters_used"]["genres"] == ["Comedy"]
        assert data["filters_used"]["year_min"] == 2018
