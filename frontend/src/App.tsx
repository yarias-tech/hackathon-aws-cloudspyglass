import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { DiagramPage } from './pages/DiagramPage';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DiagramPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
