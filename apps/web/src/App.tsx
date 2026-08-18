// SPDX-License-Identifier: Apache-2.0

import { BrowserRouter } from "react-router-dom"

import { AppRoutes } from "@/AppRoutes"

function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}

export default App
