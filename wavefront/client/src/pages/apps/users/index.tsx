import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetCurrentUser, useGetUsers } from '@app/hooks';
import { getUsersKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { IUser } from '@app/types/user';
import { useQueryClient } from '@tanstack/react-query';
import { Pencil, Trash2, Shield } from 'lucide-react';
import React, { useMemo, useState } from 'react';
import CreateUserDialog from './CreateUserDialog';
import EditUserDialog from './EditUserDialog';
import ManageAppAccessDialog from './ManageAppAccessDialog';

const UsersPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [deleteItem, setDeleteItem] = useState<IUser | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<IUser | null>(null);
  const [manageAppAccessItem, setManageAppAccessItem] = useState<IUser | null>(null);

  // Fetch users and current user
  const { data: users = [], isLoading: usersLoading } = useGetUsers();
  const { data: currentUser } = useGetCurrentUser(true);

  // Check if current user is owner
  const isOwner = useMemo(() => {
    return currentUser?.role === 'owner';
  }, [currentUser]);

  const canEditUser = (user: IUser): boolean => {
    if (!currentUser) return false;
    // User can edit themselves, or owner can edit anyone
    return user.id === currentUser.id || isOwner;
  };

  const canDeleteUser = (user: IUser): boolean => {
    if (!currentUser) return false;
    // Only owners can delete users
    // Cannot delete self
    return isOwner && user.id !== currentUser.id;
  };

  const handleDeleteClick = (e: React.MouseEvent, user: IUser) => {
    e.stopPropagation();
    setDeleteItem(user);
  };

  const handleEditClick = (e: React.MouseEvent, user: IUser) => {
    e.stopPropagation();
    setEditItem(user);
  };

  const handleManageAppsClick = (e: React.MouseEvent, user: IUser) => {
    e.stopPropagation();
    setManageAppAccessItem(user);
  };

  const handleEditSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getUsersKey() });
    setEditItem(null);
  };

  const handleDelete = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.userService.deleteUser(deleteItem.id);
      notifySuccess('User deleted successfully');
      queryClient.invalidateQueries({ queryKey: getUsersKey() });
      setDeleteItem(null);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to delete user');
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  const handleCreateUser = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getUsersKey() });
    setCreateDialogOpen(false);
  };

  const filteredUsers = users.filter((user) => {
    const query = searchQuery.toLowerCase();
    return (
      user.email.toLowerCase().includes(query) ||
      user.first_name.toLowerCase().includes(query) ||
      user.last_name.toLowerCase().includes(query)
    );
  });

  return (
    <div className="h-full w-full overflow-hidden p-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Users</h1>
          <p className="mt-2 text-gray-600">Manage user accounts</p>
        </div>
        <div className="flex items-center gap-4">
          <Input
            type="text"
            placeholder="Search users..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-[220px]"
          />
          {isOwner && (
            <Button onClick={handleCreateUser}>
              <p className="text-sm">Create User</p>
            </Button>
          )}
        </div>
      </div>

      {usersLoading ? (
        <div className="flex justify-center py-10">
          <div className="text-gray-500">Loading users...</div>
        </div>
      ) : filteredUsers.length === 0 ? (
        <div className="mt-10 flex justify-center">
          {isOwner ? (
            <EmptyStateCard
              title="No users found"
              description={searchQuery ? 'No users match your search.' : 'Get started by creating your first user'}
              actionText="Create User"
              onActionClick={handleCreateUser}
            />
          ) : (
            <EmptyStateCard
              title="No users found"
              description="No users match your search."
              actionText=""
              onActionClick={() => {}}
            />
          )}
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>First Name</TableHead>
                <TableHead>Last Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredUsers.map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="font-medium">{user.email}</TableCell>
                  <TableCell>{user.first_name}</TableCell>
                  <TableCell>{user.last_name}</TableCell>
                  <TableCell>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                        user.role === 'owner' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'
                      }`}
                    >
                      {user.role}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      {isOwner && user.role === 'app_admin' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => handleManageAppsClick(e, user)}
                          title="Manage App Access"
                        >
                          <Shield className="h-4 w-4 text-blue-600" />
                        </Button>
                      )}
                      {canEditUser(user) && (
                        <Button variant="ghost" size="sm" onClick={(e) => handleEditClick(e, user)} title="Edit">
                          <Pencil className="h-4 w-4" />
                        </Button>
                      )}
                      {canDeleteUser(user) && (
                        <Button variant="ghost" size="sm" onClick={(e) => handleDeleteClick(e, user)} title="Delete">
                          <Trash2 className="h-4 w-4 text-red-600" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete User"
        message={`Are you sure you want to delete "${deleteItem?.email}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Create User Dialog */}
      <CreateUserDialog isOpen={createDialogOpen} onOpenChange={setCreateDialogOpen} onSuccess={handleCreateSuccess} />

      {/* Edit User Dialog */}
      {editItem && (
        <EditUserDialog
          isOpen={!!editItem}
          onOpenChange={(open) => !open && setEditItem(null)}
          user={editItem}
          onSuccess={handleEditSuccess}
        />
      )}

      {/* Manage App Access Dialog */}
      {manageAppAccessItem && (
        <ManageAppAccessDialog
          isOpen={!!manageAppAccessItem}
          onOpenChange={(open) => !open && setManageAppAccessItem(null)}
          user={manageAppAccessItem}
          onSuccess={() => setManageAppAccessItem(null)}
        />
      )}
    </div>
  );
};

export default UsersPage;
