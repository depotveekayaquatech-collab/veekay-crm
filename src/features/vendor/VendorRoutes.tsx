import { Navigate, Route, Routes } from "react-router-dom";
import { VendorAuthProvider } from "@/features/vendor/VendorAuthProvider";
import { VendorLayout } from "@/features/vendor/VendorLayout";
import { VendorLoginPage } from "@/features/vendor/VendorLoginPage";
import { VendorHome } from "@/features/vendor/VendorHome";
import { VendorOrders } from "@/features/vendor/VendorOrders";
import { NewTicket, TicketDetailPage, VendorTickets } from "@/features/vendor/VendorTickets";
import { UploadDocument, VendorDocuments } from "@/features/vendor/VendorDocuments";
import { ConfirmDelivery, VendorDeliveries } from "@/features/vendor/VendorDeliveries";
import { VendorStores } from "@/features/vendor/VendorStores";
import { VendorAccount, VendorAlerts, VendorBottles } from "@/features/vendor/VendorMore";

/** Everything under /vendor: the installable app for vendor and POC logins. Has its own sign-in, separate from staff. */
export function VendorRoutes() {
  return (
    <VendorAuthProvider>
      <Routes>
        <Route path="login" element={<VendorLoginPage />} />
        <Route element={<VendorLayout />}>
          <Route index element={<VendorHome />} />
          <Route path="stores" element={<VendorStores />} />
          <Route path="orders" element={<VendorOrders />} />
          <Route path="tickets" element={<VendorTickets />} />
          <Route path="tickets/new" element={<NewTicket />} />
          <Route path="tickets/:id" element={<TicketDetailPage />} />
          <Route path="documents" element={<VendorDocuments />} />
          <Route path="documents/upload" element={<UploadDocument />} />
          <Route path="deliveries" element={<VendorDeliveries />} />
          <Route path="deliveries/new" element={<ConfirmDelivery />} />
          <Route path="bottles" element={<VendorBottles />} />
          <Route path="alerts" element={<VendorAlerts />} />
          <Route path="account" element={<VendorAccount />} />
        </Route>
        <Route path="*" element={<Navigate to="/vendor" replace />} />
      </Routes>
    </VendorAuthProvider>
  );
}
