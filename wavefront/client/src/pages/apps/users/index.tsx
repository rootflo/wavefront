import AppsBackdrop from '@app/components/AppsBackdrop';
import { toneClass } from '@app/lib/tones';
import { ResourceListSkeleton } from '@app/components/ResourceList';
import ListHeader from '@app/components/ListHeader';
import ResourceCard from '@app/components/ResourceCard';
import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetConsoleUsers, useGetCurrentUser } from '@app/hooks';
import { getConsoleUsersKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { IUser } from '@app/types/user';
import { useQueryClient } from '@tanstack/react-query';
import { Pencil, Trash2, Shield, User } from 'lucide-react';
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

  // Fetch console users and current user
  const { data: consoleUsers = [], isLoading: consoleUsersLoading } = useGetConsoleUsers();
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
    queryClient.invalidateQueries({ queryKey: getConsoleUsersKey() });
    setEditItem(null);
  };

  const handleDelete = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.userService.deleteUser(deleteItem.id);
      notifySuccess('User deleted successfully');
      queryClient.invalidateQueries({ queryKey: getConsoleUsersKey() });
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
    queryClient.invalidateQueries({ queryKey: getConsoleUsersKey() });
    setCreateDialogOpen(false);
  };

  const filteredUsers = consoleUsers.filter((user) => {
    const query = searchQuery.toLowerCase();
    return (
      user.email.toLowerCase().includes(query) ||
      user.first_name.toLowerCase().includes(query) ||
      user.last_name.toLowerCase().includes(query)
    );
  });

  return (
    <div className="relative isolate h-full w-full overflow-hidden p-4 max-md:overflow-y-auto sm:p-8">
      <AppsBackdrop />
      <ListHeader
        title="Users"
        count={filteredUsers.length || undefined}
        subtitle={<>Manage user accounts</>}
        search={{ value: searchQuery, onChange: setSearchQuery, placeholder: 'Search users...' }}
        primary={isOwner ? { label: 'Create user', onClick: handleCreateUser } : undefined}
      />

      {consoleUsersLoading ? (
        <ResourceListSkeleton view="table" />
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
        <div className="frost-panel ring-frost-border overflow-x-auto rounded-xl border ring-1">
          <div data-mobile-cards className="flex flex-col gap-3 pb-24 md:hidden">
            {filteredUsers.map((user) => (
              <ResourceCard
                key={user.id}
                icon={User}
                title={user.email}
                description={`${user.first_name} ${user.last_name}`.trim() || undefined}
                metadata={[
                  {
                    label: 'Role',
                    value: user.role,
                    className:
                      user.role === 'owner'
                        ? 'bg-purple-500/15 text-purple-700 dark:text-purple-300'
                        : 'bg-blue-500/15 text-blue-700 dark:text-blue-300',
                  },
                ]}
                onEditClick={canEditUser(user) ? (e) => handleEditClick(e, user) : undefined}
                onDeleteClick={canDeleteUser(user) ? (e) => handleDeleteClick(e, user) : undefined}
                deleteTitle="Delete user"
                extraActions={
                  isOwner && user.role === 'app_admin'
                    ? [{ label: 'Manage app access', icon: Shield, onClick: (e) => handleManageAppsClick(e, user) }]
                    : []
                }
              />
            ))}
          </div>
          <div className="max-md:hidden">
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
                          user.role === 'owner' ? toneClass.violet : toneClass.info
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
